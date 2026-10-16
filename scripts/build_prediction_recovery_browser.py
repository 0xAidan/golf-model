#!/usr/bin/env python3
"""Build a private, offline browser for a preserved forecast index generation.

This presents source observations; it never imports, grades or mutates forecasts.
No libraries, analytics, fonts or other resources are loaded from the internet.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


TEMPLATE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>Recovered forecasts · Golf Model</title>
<style>
:root{color-scheme:light;--paper:#f5f3ec;--ink:#182e26;--muted:#617068;--line:#d7ddd3;--green:#244d3c;--white:#fffcf5}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,sans-serif}button,input,select{font:inherit;color:inherit}button,select{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #b28224;outline-offset:3px}button{border:1px solid var(--line);background:var(--white);padding:10px 15px;border-radius:6px}button:hover{background:#e4eadf}button:disabled{cursor:default;opacity:.45}header{padding:38px max(24px,calc((100vw - 1420px)/2));background:var(--ink);color:#f2f4e9}.eyebrow{font-size:11px;letter-spacing:.17em;text-transform:uppercase;font-weight:650;margin:0 0 10px}h1{font-size:clamp(30px,4vw,48px);font-weight:500;letter-spacing:-.055em;line-height:1.1;margin:0 0 16px}header p{color:#c4d1c6;max-width:800px;margin:8px 0}.counts{display:flex;gap:40px;margin-top:25px;font-size:12px}.counts strong{display:block;font-weight:500;font-size:25px;font-variant-numeric:tabular-nums;color:#fff}.layout{max-width:1468px;margin:auto;padding:30px 24px;display:grid;grid-template-columns:245px minmax(0,1fr);gap:30px}.filters{display:flex;flex-direction:column;gap:16px;position:sticky;top:20px;max-height:calc(100vh - 40px);overflow:auto;align-self:start}label{display:grid;gap:5px;font-size:12px;font-weight:600}input,select{width:100%;border:1px solid #bac7bb;border-radius:5px;background:var(--white);padding:10px;font-size:13px}h2{font-size:18px;margin:0;font-weight:550}small,.muted{color:var(--muted)}.note{font-size:12px;color:var(--muted);margin:0}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:14px}.toolbar p{margin:0;font-size:12px}.table-wrap{overflow:auto;border-top:2px solid var(--green)}table{border-collapse:collapse;width:100%;font-size:13px}thead{font-size:10px;text-transform:uppercase;letter-spacing:.08em}th{text-align:left;padding:13px 10px;border-bottom:1px solid var(--line);white-space:nowrap}td{padding:13px 10px;border-bottom:1px solid var(--line);vertical-align:top}td:nth-child(2){min-width:170px}.player{font-weight:600}.secondary{display:block;font-size:11px;color:var(--muted);margin-top:4px}.open{padding:4px 8px;font-size:11px}.empty{padding:40px;text-align:center}.pager{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 0;font-size:12px}details{padding:16px 0;border-top:1px solid var(--line);font-size:12px}summary{cursor:pointer;font-weight:600}details p{margin-bottom:0}a{color:var(--green);overflow-wrap:anywhere}dialog{border:1px solid var(--line);border-radius:12px;padding:0;max-width:880px;width:calc(100vw - 30px);max-height:90vh;background:var(--white);color:var(--ink)}dialog::backdrop{background:#11251dc9}.dialog-head{position:sticky;top:0;background:var(--white);display:flex;justify-content:space-between;align-items:start;padding:20px 24px;border-bottom:1px solid var(--line);gap:20px}.dialog-body{padding:0 24px 24px;overflow-wrap:anywhere}.dialog-body h3{margin:24px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.1em}pre{white-space:pre-wrap;font:12px/1.6 ui-monospace,monospace;background:#eaf0e5;padding:16px;border-radius:6px;overflow-wrap:anywhere}dl{display:grid;grid-template-columns:130px minmax(0,1fr);font-size:12px;gap:8px}dt{color:var(--muted)}dd{margin:0}ol{padding-left:20px;font-size:12px}li{margin:12px 0}.status{font-size:11px;background:#e6dfcc;padding:4px 8px;display:inline-block;border-radius:4px}footer{max-width:1420px;margin:0 auto;padding:0 24px 35px;font-size:11px;color:var(--muted)}
@media(max-width:760px){header{padding:28px 20px}.layout{display:block;padding:22px 16px}.filters{position:static;max-height:none;display:grid;grid-template-columns:1fr 1fr;margin-bottom:24px}.filters h2,.filters .note,.filters details{grid-column:1/-1}.counts{gap:22px}.counts strong{font-size:20px}.toolbar{align-items:start}dl{grid-template-columns:95px minmax(0,1fr)}th,td{padding:12px 7px}.dialog-head,.dialog-body{padding-left:16px;padding-right:16px}}
</style>
<header><p class="eyebrow">Golf Model / Private recovery</p><h1>Recovered forecasts</h1><p>Search the original card and snapshot observations recovered from your Mac, Cursor, Git and server. Each row leads back to exact source text or JSON and every preserved copy.</p><p style="font-size:12px">Recovery is incomplete. Versions, refreshes and research outputs are retained separately; observation counts are not bets or verified performance.</p><div class="counts" id="counts"></div></header>
<main class="layout"><aside class="filters" aria-label="Forecast filters"><h2>Find a forecast</h2>
<label>Search<input id="query" type="search" placeholder="Player, event, odds, source…"></label>
<label>Event label<select id="event" aria-label="Event label"><option value="">All event labels</option></select></label>
<label>Observation type<select id="kind" aria-label="Observation type"><option value="">All types</option></select></label>
<label>Source context<select id="context" aria-label="Source context"><option value="all">All preserved observations</option><option value="cards">Original card candidates</option><option value="json">Saved JSON rows</option><option value="other">Other source contexts</option></select></label>
<label>Content status<select id="status" aria-label="Content status"><option value="">All content statuses</option></select></label>
<button id="reset">Clear filters</button><p class="note">Event labels and generation times are shown as written. A matching name does not verify the tour, event date, model version or pre-event publication.</p>
<details><summary>What is included?</summary><p>Supported player tables, priced selections, matchup projections, watch/fade notes and saved JSON forecast arrays. Unparsed source material and full database vaults remain in the recovery folders; they are not all represented as rows here.</p><p>No stakes, settlements, ROI or closing lines are inferred by this browser.</p></details>
</aside><section aria-label="Recovered forecast observations"><div class="toolbar"><div><h2 id="result-title">All observations</h2><p id="result-count" role="status" aria-live="polite"></p></div><button id="download">Export filtered JSON</button></div>
<div class="table-wrap"><table><thead><tr><th>Event / source time</th><th>Player / selection</th><th>Type / context</th><th>Reference</th><th><span aria-label="Inspect observation">Inspect</span></th></tr></thead><tbody id="rows"></tbody></table></div><div class="pager"><button id="previous">← Previous</button><span id="page"></span><button id="next">Next →</button></div>
<details><summary>Recovery gaps and database vaults</summary><p>All 93 targeted original paths and the old Documents database have now been preserved. Other cloud-only files remain uncollected, mostly research artifacts. The full PGA Championship field has not been recovered; a partial May 12 screenshot survives. No original published 2025 card is confirmed. Most recovered cards span February–October 2026.</p><p>The hidden local database, old server worktree and current production snapshot are preserved independently, including source IDs and all original tables. Their millions of repeated database observations are deliberately outside this card/snapshot browser. Read the <a href="__AUDIT_URL__">recovery report</a> for exact paths, coverage and limitations.</p></details>
</section></main><footer>Offline artifact. No network connections, tracking, source modifications or model changes. Built from immutable source-index generations; see <a href="recovery-browser-manifest.json">manifest</a>.</footer>
<dialog id="inspection" aria-labelledby="inspect-title"><div class="dialog-head"><div><p class="eyebrow">Preserved source observation</p><h2 id="inspect-title"></h2></div><button id="close" aria-label="Close source inspection">Close</button></div><div class="dialog-body" id="inspection-body"></div></dialog>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('payload').textContent),el=id=>document.getElementById(id),PAGE=100;
const pretty=s=>String(s||'Unspecified').replaceAll('_',' '),number=n=>n.toLocaleString();
const controlIds=['query','event','kind','context','status'];let page=0,filtered=data.rows;
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n}
for(const [value,label] of [[data.rows.length,'indexed observations'],[Object.keys(data.sources).length,'source payloads with observations'],[data.metrics.total_payloads,'preserved Markdown / JSON payloads']]){const n=node('div',label);n.prepend(node('strong',number(value)));el('counts').append(n)}
function options(id,values){for(const value of [...new Set(values)].sort((a,b)=>a.localeCompare(b))){if(value){const o=node('option',id==='kind'?pretty(value):value);o.value=value;el(id).append(o)}}}
options('event',data.rows.map(r=>r.event_label||''));options('kind',data.rows.map(r=>r.kind));options('status',data.rows.flatMap(r=>r.content_statuses||[]));
const searchable=data.rows.map(r=>JSON.stringify([r.event_label,r.player_label,r.fields,r.payload,r.raw_text,r.section,r.generated_label,r.source_kinds,data.sources[r.source_sha256].references]).toLowerCase());
function apply(){const q=el('query').value.trim().toLowerCase(),event=el('event').value,kind=el('kind').value,context=el('context').value,status=el('status').value;filtered=data.rows.filter((r,i)=>(!q||searchable[i].includes(q))&&(!event||r.event_label===event)&&(!kind||r.kind===kind)&&(!status||(r.content_statuses||[]).includes(status))&&(context==='all'||(context==='cards'&&r.artifact_role==='original_card')||(context==='json'&&!!r.json_pointer)||(context==='other'&&r.artifact_role!=='original_card'&&!r.json_pointer)));page=0;render()}
function render(){el('result-title').textContent=el('event').value||'All observations';el('result-count').textContent=number(filtered.length)+' matching observations · '+number(new Set(filtered.map(r=>r.source_sha256)).size)+' source payloads';el('rows').replaceChildren();for(const r of filtered.slice(page*PAGE,(page+1)*PAGE)){const tr=node('tr');let td=node('td',r.event_label||'Unresolved event');td.append(node('span',r.generated_label||'Source time not supplied','secondary'));tr.append(td);td=node('td',r.player_label||'Source-written selection','player');const f=r.fields||r.payload||{};const detail=[f.market,f.opponent?('vs '+f.opponent):'',f.odds?('Odds '+f.odds):'',f.rank?('Rank '+f.rank):''].filter(Boolean).join(' · ');if(detail)td.append(node('span',detail,'secondary'));tr.append(td);td=node('td',pretty(r.kind));td.append(node('span',pretty(r.artifact_role||(r.source_kinds||[]).join(', ')),'secondary'));tr.append(td);td=node('td',r.json_pointer||('Line '+r.line));td.append(node('span',r.source_sha256.slice(0,12)+'…','secondary'));tr.append(td);td=node('td');const b=node('button','Source','open');b.setAttribute('aria-label','Inspect '+(r.player_label||'selection')+' at '+(r.event_label||'unresolved event'));b.onclick=()=>inspect(r);td.append(b);tr.append(td);el('rows').append(tr)}if(!filtered.length){const tr=node('tr'),td=node('td','No observations match these filters.','empty');td.colSpan=5;tr.append(td);el('rows').append(tr)}const pages=Math.max(1,Math.ceil(filtered.length/PAGE));el('page').textContent=(page+1)+' / '+pages;el('previous').disabled=page===0;el('next').disabled=page+1>=pages}
function inspect(r){el('inspect-title').textContent=(r.player_label||'Selection')+' · '+(r.event_label||'Unresolved event');const body=el('inspection-body');body.replaceChildren();body.append(node('p','Pre-event publication and settlement are not certified by this index.','status'));const dl=node('dl');for(const [key,value] of [['Type',pretty(r.kind)],['Context',pretty(r.artifact_role||(r.source_kinds||[]).join(', '))],['Content',pretty((r.content_statuses||[]).join(', '))],['Generated label',r.generated_label||'Not supplied'],['Reference',r.json_pointer||('Line '+r.line)],['SHA-256',r.source_sha256]]){dl.append(node('dt',key),node('dd',value))}body.append(dl,node('h3',r.json_pointer?'Original JSON row':'Original source line'),node('pre',r.raw_text||JSON.stringify(r.payload,null,2)));if(r.headers){body.append(node('h3','Source column labels'),node('pre',r.headers.join(' | ')))}if(r.section)body.append(node('h3','Source section'),node('p',r.section));body.append(node('h3','Every preserved source reference'));const ol=node('ol');const source=data.sources[r.source_sha256];for(const ref of source.references){const li=node('li',ref.source_path);if(ref.resolved_corpus_path||ref.corpus_path)li.append(node('span','Preserved payload: '+(ref.resolved_corpus_path||ref.corpus_path),'secondary'));if(ref.source_kind)li.append(node('span',pretty(ref.source_kind),'secondary'));if(ref.captured_at)li.append(node('span','Captured: '+ref.captured_at+' (not publication time)','secondary'));if(ref.source_card_path)li.append(node('span','Referenced card: '+ref.source_card_path,'secondary'));const extra=node('details');extra.append(node('summary','Complete provenance metadata'),node('pre',JSON.stringify(ref,null,2)));li.append(extra);ol.append(li)}body.append(ol);el('inspection').showModal()}
for(const id of controlIds)el(id).addEventListener(id==='query'?'input':'change',apply);el('previous').onclick=()=>{if(page>0){page--;render()}};el('next').onclick=()=>{if((page+1)*PAGE<filtered.length){page++;render()}};el('reset').onclick=()=>{for(const id of controlIds)el(id).value=id==='context'?'all':'';apply()};el('close').onclick=()=>el('inspection').close();el('inspection').addEventListener('click',e=>{if(e.target===el('inspection'))el('inspection').close()});el('download').onclick=()=>{const hashes=new Set(filtered.map(r=>r.source_sha256)),sources=Object.fromEntries([...hashes].map(h=>[h,data.sources[h]]));const blob=new Blob([JSON.stringify({basis:'preserved_observations_not_independent_wagers',rows:filtered,sources},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='recovered-forecast-observations.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};render();
</script></html>'''


def build(markdown: Path, structured: Path, output: Path, audit: Path) -> dict:
    """Read immutable indexes and exclusively create one portable HTML artifact."""
    indexes = [markdown / 'archive-index.json', structured / 'structured-archive-index.json']
    rows_paths = [markdown / 'prediction-observations.jsonl', structured / 'structured-prediction-observations.jsonl']
    rows = [json.loads(line) for path in rows_paths for line in path.read_text().splitlines() if line]
    used_hashes = {row['source_sha256'] for row in rows}
    sources = {}
    total_payloads = 0
    all_hashes = set()
    for path in indexes:
        index = json.loads(path.read_text())
        total_payloads += index['source_files']
        for item in index['files']:
            digest = item['sha256']
            all_hashes.add(digest)
            if digest not in used_hashes:
                continue
            sources[digest] = {'references': item['sources']}
    if used_hashes != set(sources):
        raise ValueError('Missing provenance for one or more observations')
    # Keep complete original fields while omitting only repetitive derived index flags.
    def row_order(row: dict) -> tuple:
        pointer = row.get('json_pointer', '')
        natural_pointer = tuple((1, int(part)) if part.isdigit() else (0, part) for part in re.split(r'(\d+)', pointer))
        return (not bool(row.get('event_label')), (row.get('event_label') or '').casefold(), row.get('generated_label') or '', row['source_sha256'], row.get('line', 0), natural_pointer)

    rows.sort(key=row_order)
    payload = json.dumps({'rows': rows, 'sources': sources, 'metrics': {'total_payloads': len(all_hashes)}}, separators=(',', ':'), ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = TEMPLATE.replace('__PAYLOAD__', payload).replace('__AUDIT_URL__', 'recovery-report.md')
    inputs = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in indexes + rows_paths}
    manifest = {'schema_version': 1, 'basis': 'preserved_observations_not_independent_wagers', 'inputs_sha256': inputs, 'observations': len(rows), 'source_payloads_with_observations': len(sources), 'total_indexed_payloads': len(all_hashes), 'format_index_entries': total_payloads, 'kinds': dict(Counter(r['kind'] for r in rows)), 'output_sha256': hashlib.sha256(html.encode()).hexdigest(), 'network_connections': False, 'source_mutations': False}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'recovered-forecasts.html').write_text(html)
    (output / 'recovery-browser-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'recovery-report.md').write_text(audit.read_text())
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--markdown', type=Path, required=True)
    parser.add_argument('--structured', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.markdown, args.structured, args.output, args.audit), indent=2))
