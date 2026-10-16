#!/usr/bin/env python3
"""Build or verify a private, isolated weekly learning release; never install or train."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SEED = "data/research/verified-learning-corpus-v2-identity-repair.jsonl.gz"
SEED_SHA256 = "77fa175573bd03b214984de193e20466ecb4c0f045e7bd3e9a3b6ab722afb418"
BASELINE = "config/model-baselines/original-453f49ec24f0e48a.json"
MANIFEST = "release-manifest.json"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def baseline_verified(root: Path) -> dict:
    baseline = json.loads((root / BASELINE).read_text())
    payload = {k: v for k, v in baseline.items() if k != "hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(canonical).hexdigest() != baseline["hash"]:
        raise ValueError("Pinned baseline manifest changed")
    for name, expected in baseline["source_hashes"].items():
        if digest(root / name) != expected:
            raise ValueError(f"Pinned baseline source changed: {name}")
    return baseline


def safe_relative(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and not any(part.startswith(".") for part in path.parts)


def source_files(root: Path) -> list[str]:
    names = set()
    for package in ("src", "backtester"):
        names.update(path.relative_to(root).as_posix() for path in (root / package).rglob("*.py")
                     if not any(part.startswith(".") for part in path.relative_to(root).parts))
    names.update({
        "scripts/train_learning_challenger.py", "scripts/weekly_learning_refresh.py",
        "scripts/package_learning_release.py", BASELINE, SEED,
        "config/learning-protocols/recovered-rounds-v2.json",
        "config/learning-protocols/recovered-rounds-v2-identity-repair.json",
        "docs/research/sealed_holdout_events.json",
        "deploy/systemd/golf-learning-refresh.service", "deploy/systemd/golf-learning-refresh.timer",
        "requirements.txt",
    })
    names.update(json.loads((root / BASELINE).read_text())["source_hashes"])
    for name in names:
        path = root / name
        if not safe_relative(name) or path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
            raise ValueError(f"Not an allowed regular release input: {name}")
    return sorted(names)


def verify_release(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / MANIFEST).read_text())
    listed = set()
    for item in manifest["files"]:
        name = item["path"]
        path = root / name
        if (not safe_relative(name) or name in listed or path.is_symlink() or not path.is_file()
                or root not in path.resolve().parents or path.stat().st_size != item["bytes"]
                or digest(path) != item["sha256"]):
            raise ValueError(f"Release file verification failed: {name}")
        listed.add(name)
    for package in ("src", "backtester", "scripts"):
        actual = {path.relative_to(root).as_posix() for path in (root / package).rglob("*.py")}
        if not actual <= listed:
            raise ValueError("Unlisted Python implementation in isolated release")
    if (root / ".env").exists() or digest(root / SEED) != SEED_SHA256:
        raise ValueError("Private seed changed or an environment file was introduced")
    baseline = baseline_verified(root)
    payload = hashlib.sha256(encoded(manifest["files"])).hexdigest()
    if payload != manifest["payload_sha256"] or baseline["hash"] != manifest["baseline_hash"]:
        raise ValueError("Release manifest identity mismatch")
    return {"state": "verified", "release_id": manifest["release_id"], "files": len(listed),
            "payload_sha256": payload, "seed_sha256": SEED_SHA256, "baseline_hash": baseline["hash"]}


def write_tar(root: Path, destination: Path, manifest: dict) -> None:
    names = sorted([item["path"] for item in manifest["files"]] + [MANIFEST])
    with destination.open("xb") as raw:
        os.chmod(destination, 0o600)
        with gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name in names:
                    content = (root / name).read_bytes()
                    item = tarfile.TarInfo(name)
                    item.size, item.mtime, item.uid, item.gid = len(content), 0, 0, 0
                    item.uname = item.gname = ""
                    item.mode = 0o600 if name == SEED else 0o644
                    archive.addfile(item, io.BytesIO(content))


def verify_tar(path: Path, manifest: dict) -> None:
    expected = {item["path"]: item["sha256"] for item in manifest["files"]}
    expected[MANIFEST] = hashlib.sha256(encoded(manifest)).hexdigest()
    observed = set()
    with tarfile.open(path, "r:gz") as archive:
        for item in archive:
            if not item.isfile() or item.name in observed or item.name not in expected:
                raise ValueError("Unexpected release archive member")
            handle = archive.extractfile(item)
            if hashlib.file_digest(handle, "sha256").hexdigest() != expected[item.name]:
                raise ValueError(f"Release archive member hash mismatch: {item.name}")
            observed.add(item.name)
    if observed != set(expected):
        raise ValueError("Release archive file set is incomplete")


def smoke(root: Path, staging: Path) -> dict:
    source = staging / "smoke-source" / "not-created.sqlite"
    env = {name: value for name, value in os.environ.items() if name in {"PATH", "LANG", "LC_ALL", "TMPDIR"}}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "GOLF_APP_ROOT": str(root),
                "GOLF_DATA_DIR": str(source.parent), "GOLF_DB_PATH": str(source),
                "PRESERVE_PREDICTION_HISTORY": "1", "TRACK_PROMOTION_ENABLED": "0"})
    program = r'''
import json,sys
from pathlib import Path
release=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(release))
from src import db
from backtester import learning_challenger as legacy, learning_challenger_v2 as trainer
from backtester import learning_corpus,pit_models,sealed_holdout
from scripts import weekly_learning_refresh as weekly
assert legacy.ROOT==trainer.ROOT==sealed_holdout.ROOT==release
assert trainer.PROTOCOL_PATH.is_relative_to(release)
assert all(Path(m.__file__).is_relative_to(release) for m in (db,legacy,trainer,learning_corpus,pit_models,sealed_holdout,weekly))
assert legacy.preserve_baseline({}, {})['preserved'] is True
assert sealed_holdout.sealed_event_keys()
captured=[]
weekly.train_main=lambda args:captured.append(args) or 0
assert weekly.main([])==0
args=captured[0]
assert args[args.index('--seed-cache')+1]==str(release/'data/research/verified-learning-corpus-v2-identity-repair.jsonl.gz')
assert args[args.index('--output')+1]==str(release/'data/research/learning-runs')
assert args[args.index('--protocol')+1]=='recovered-v2'
assert not Path(db.DB_PATH).exists()
print(json.dumps({'isolated_imports':True,'baseline_verified':True,'sealed_policy_loaded':True,'seed_default_isolated':True,'default_output_private':True,'database_created':False}))
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(root)], cwd=staging,
                            env=env, check=True, capture_output=True, text=True, timeout=60)
    checked = json.loads(result.stdout)
    for entry in ("train_learning_challenger.py", "weekly_learning_refresh.py"):
        parsed = subprocess.run([sys.executable, "-I", "-B", str(root / "scripts" / entry), "--help"],
                                cwd=staging, env=env, check=True, capture_output=True, text=True, timeout=60)
        if "--seed-cache" not in parsed.stdout or "--public-report" not in parsed.stdout:
            raise ValueError("Isolated CLI parser smoke failed")
    if source.exists() or (root / "data" / "golf.db").exists():
        raise ValueError("Smoke test unexpectedly created a source database")
    return {**checked, "cli_parsers": 2, "training_executed": False, "python": sys.version}


def build(root: Path, staging: Path, prefix: str) -> dict:
    root, staging = root.resolve(), staging.resolve()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", prefix):
        raise ValueError("Release prefix must be a short path-safe label")
    public_roots = [root / "output", root / "static", root / "frontend/public", root / "frontend/dist"]
    if staging == root or any(path == staging or path in staging.parents for path in public_roots):
        raise ValueError("Release staging must be outside public output and asset trees")
    baseline = baseline_verified(root)
    if digest(root / SEED) != SEED_SHA256:
        raise ValueError("Verified identity-repair seed hash mismatch")
    files = [{"path": name, "bytes": (root / name).stat().st_size, "sha256": digest(root / name),
              "mode": "0600" if name == SEED else "0644"} for name in source_files(root)]
    payload = hashlib.sha256(encoded(files)).hexdigest()
    release_id = f"{prefix}-{payload[:16]}"
    manifest = {"schema_version": 1, "release_id": release_id, "payload_sha256": payload,
                "baseline_hash": baseline["hash"], "seed_sha256": SEED_SHA256, "files": files,
                "layout": {"release": f"/opt/golf-learning/releases/{release_id}", "current": "/opt/golf-learning/current",
                           "private_runs": "/opt/golf-learning/runs", "source_database": "/opt/golf-model/data/golf.db",
                           "source_snapshot": "/opt/golf-model/data/live_refresh_snapshot.json",
                           "public_report": "/opt/golf-model/frontend/dist/reports/learning-latest.json"},
                "private_directory_modes": {"/opt/golf-learning": "0700", "/opt/golf-learning/releases": "0700", "/opt/golf-learning/runs": "0700"},
                "automatic_promotion": False, "raw_database_bundled": False, "environment_files_bundled": False}
    staging.mkdir(parents=True, exist_ok=True)
    os.chmod(staging, 0o700)
    if shutil.disk_usage(staging).free < sum(item["bytes"] for item in files) * 3 + 1024 ** 3:
        raise ValueError("Insufficient private staging space with 1 GiB reserve")
    release = staging / release_id
    release.mkdir(mode=0o700, exist_ok=True)
    for item in files:
        target = release / item["path"]
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not target.exists():
            with (root / item["path"]).open("rb") as source, target.open("xb") as dest:
                shutil.copyfileobj(source, dest)
            os.chmod(target, int(item["mode"], 8))
        if digest(target) != item["sha256"]:
            raise ValueError("Release inputs changed while staging; no bundle produced")
    path = release / MANIFEST
    if not path.exists():
        with path.open("xb") as handle:
            handle.write(encoded(manifest))
    if path.read_bytes() != encoded(manifest):
        raise ValueError("Existing staged manifest differs; source is retained")
    verification = verify_release(release)
    checked = smoke(release, staging)
    bundle = staging / f"{release_id}.tar.gz"
    if not bundle.exists():
        write_tar(release, bundle, manifest)
    verify_tar(bundle, manifest)
    result = {"state": "prepared_not_installed", "release_id": release_id, "release_path": str(release),
              "bundle": str(bundle), "bundle_bytes": bundle.stat().st_size, "bundle_sha256": digest(bundle),
              "manifest": str(path), "manifest_sha256": digest(path), "verification": verification, "smoke": checked}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with (staging / f"validation-{stamp}.json").open("xb") as handle:
        handle.write(encoded(result))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-release", type=Path, help="Read-only integrity check used by the service preflight")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--staging", type=Path, help="Private staging directory outside public output")
    parser.add_argument("--prefix", default="20261016-learning-isolated")
    args = parser.parse_args(argv)
    if args.verify_release:
        result = verify_release(args.verify_release)
    else:
        if not args.staging:
            parser.error("--staging is required when building")
        result = build(args.root, args.staging, args.prefix)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
