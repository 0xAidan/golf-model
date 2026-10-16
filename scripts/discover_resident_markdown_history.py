#!/usr/bin/env python3
"""Bounded, resident-only golf Markdown content search from retained full file lists."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.discover_local_history import Collector, CONTENT_HINT, EXCLUDED, NAME_HINT, SECRET_HINT

GOLF_CONTEXT = re.compile(r"\bgolf\b|\bPGA\b|Data\s?Golf|\bDP World Tour\b|\bKorn Ferry\b|\bTPC\b|Augusta National|Scottie Scheffler|Rory McIlroy|Xander Schauffele|Collin Morikawa|Hideki Matsuyama|Patrick Cantlay|Sungjae Im|Viktor Hovland|\bSG[:_]\s*(?:OTT|APP|ARG|PUTT)\b", re.I)
FORECAST_CONTENT = re.compile(r"betting card|power rankings|model rankings|\|[^\n]*(?:player|golfer|pick)[^\n]*\|[^\n]*(?:rank|odds|EV|prob|composite)|(?:[-*]\s+)?\*\*[^\n]+\*\*[^\n]*(?:[+-]\d{3,}|model\s+\d+(?:\.\d+)?%)", re.I)
MAX_BYTES = 2 * 1024 * 1024
RESERVE = 1024 ** 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paths-json', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=180)
    args = parser.parse_args()
    start = time.monotonic()
    deadline = start + min(180, args.seconds)
    if args.output.exists():
        raise FileExistsError('Choose a new additive discovery generation')
    counts, roots, inputs, errors = Counter(), defaultdict(Counter), [], []
    paths = set()
    for path in args.paths_json:
        raw = path.read_bytes()
        listing = json.loads(gzip.decompress(raw) if path.name.endswith('.gz') else raw)
        paths.update(listing)
        inputs.append({'path': str(path), 'file_sha256': hashlib.sha256(raw).hexdigest(), 'listed_paths': len(listing)})
    collector = Collector(args.output)
    candidates = sorted(p for p in paths if p.lower().endswith(('.md', '.markdown')))
    home = Path.home()
    def bucket(text):
        try:
            relative = Path(text).relative_to(home)
            if relative.parts[:3] == ('Library', 'Mobile Documents', 'com~apple~CloudDocs'):
                return 'iCloud Drive'
            return relative.parts[0]
        except (ValueError, IndexError):
            return 'outside_home'
    def count(key, text):
        counts[key] += 1
        roots[bucket(text)][key] += 1
    def timeout(_signum, _frame):
        raise TimeoutError('resident read timed out')
    signal.signal(signal.SIGALRM, timeout)
    last_progress = time.monotonic()
    for text in candidates:
        if time.monotonic() >= deadline - 2:
            counts['deadline_reached'] = 1
            break
        count('listed_markdown_considered', text)
        if (SECRET_HINT.search(text) or any(f'/{part}/' in text for part in EXCLUDED)
            or '.app/' in text or '/Library/Caches/' in text or '/Library/Application Support/' in text
            or '/golf-model-preservation/' in text or '/golf-model-reconciliation/' in text
            or '/.Trash/' in text):
            count('excluded_path', text)
            continue
        fd = None
        signal.setitimer(signal.ITIMER_REAL, min(2, max(0.05, deadline - time.monotonic() - 1)))
        try:
            path = Path(text)
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                count('skipped_nonregular_or_symlink', text)
                continue
            if metadata.st_size > MAX_BYTES:
                count('skipped_over_2MiB', text)
                continue
            if getattr(metadata, 'st_flags', 0) & 0x40000000 or (metadata.st_size and not metadata.st_blocks):
                count('skipped_dataless_without_read', text)
                continue
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | os.O_NONBLOCK)
            current = os.fstat(fd)
            if getattr(current, 'st_flags', 0) & 0x40000000 or (current.st_size and not current.st_blocks):
                count('skipped_dataless_after_open', text)
                continue
            chunks, size = [], 0
            while size <= MAX_BYTES:
                chunk = os.read(fd, min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            data = b''.join(chunks)
            after = os.fstat(fd)
            if size != current.st_size or current.st_size != after.st_size or current.st_mtime_ns != after.st_mtime_ns:
                count('skipped_changed_during_read', text)
                continue
            count('resident_content_read', text)
            counts['resident_bytes_read'] += len(data)
            content = data.decode('utf-8', errors='replace')
            # Generic ranking/odds tables need independent golf context so an
            # unrelated sport's Markdown is never copied to this corpus.
            matches = bool(GOLF_CONTEXT.search(content) and (CONTENT_HINT.search(content) or FORECAST_CONTENT.search(content)))
            if not matches:
                count('resident_negative_content', text)
                continue
            if shutil.disk_usage(args.output).free < RESERVE + len(data) * 2 + 1024 * 1024:
                count('matched_but_reserve_blocked', text)
                errors.append({'source': text, 'error': '1GiB reserve would be breached'})
                continue
            collector.markdown(data, text, mtime_ns=current.st_mtime_ns,
                               discovery_method='resident_markdown_content_search',
                               outside_golf_named_path=not bool(NAME_HINT.search(text)),
                               content_match='golf_context_and_forecast_or_content_hint',
                               read_verified_resident=True)
            count('golf_content_matches_preserved', text)
            if not NAME_HINT.search(text):
                count('matches_outside_golf_named_paths', text)
        except (OSError, ValueError, TimeoutError) as exc:
            count('metadata_or_read_error', text)
            errors.append({'source': text, 'error': str(exc)})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if fd is not None:
                os.close(fd)
        if time.monotonic() - last_progress >= 35:
            print(json.dumps({'elapsed_seconds': round(time.monotonic()-start, 1), 'counts': counts}), flush=True)
            last_progress = time.monotonic()
    collector.save([])
    report = {'schema_version': 1, 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'mode': 'read_only_resident_content_search_no_hydration', 'inputs': inputs,
              'unique_listed_paths': len(paths), 'listed_markdown_candidates': len(candidates),
              'elapsed_seconds': round(time.monotonic()-start, 3), 'max_seconds': min(180,args.seconds),
              'counts': dict(counts), 'by_home_root': {k: dict(v) for k,v in sorted(roots.items())},
              'errors': errors, 'free_bytes_after': shutil.disk_usage(args.output).free,
              'corpus_sources': len(collector.entries), 'distinct_hashes': len({r['sha256'] for r in collector.entries}),
              'limitations': ['Input listings were previously bounded/partial; this does not claim an exhaustive filesystem traversal.',
                             'Only resident regular non-symlink Markdown <=2MiB was read. Placeholders, larger files, dependencies, caches and secret paths were skipped.',
                             'Negative read attempts are counted by root; their unrelated contents are not retained.',
                             'Original source bytes were never changed; matches are additive gzip copies.']}
    (args.output/'resident-content-scan-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2), flush=True)


if __name__ == '__main__':
    main()
