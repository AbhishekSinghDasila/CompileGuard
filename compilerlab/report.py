"""Offline, self-contained campaign dashboard; no network or service required."""
from collections import Counter
import html
import json
from pathlib import Path


def render(store, directory):
    folder = Path(directory).resolve()
    rows = store.rows()
    counts = Counter((row['report'] or {}).get('status', row['state'].upper()) for row in rows)
    features = sorted({op for row in rows for op, _ in row['payload']['case']['ops']})
    summary = {'jobs': len(rows), 'counts': dict(counts), 'operation_coverage': features,
               'cases': len({r['payload']['case_id'] for r in rows}),
               'profiles': sorted({r['payload']['profile']['name'] for r in rows}),
               'native_passes': sum((r['report'] or {}).get('status') == 'PASS' and r['payload']['profile']['backend'] != 'model' for r in rows),
               'model_passes': sum((r['report'] or {}).get('status') == 'PASS' and r['payload']['profile']['backend'] == 'model' for r in rows)}
    body = []
    for row in rows:
        payload, report = row['payload'], row['report'] or {}
        case, p = payload['case'], payload['profile']
        status = report.get('status', row['state'].upper())
        artifact = Path(row['artifact']) if row['artifact'] else None
        link = ''
        if artifact and artifact.is_relative_to(folder):
            from urllib.parse import quote
            relative = quote((artifact.relative_to(folder) / 'report.json').as_posix())
            link = f'<a href="{relative}">Evidence</a>'
        values = [row['id'][:10], str(case.get('seed', 'saved')), p['name'], case.get('kind', 'map'),
                  status, str(report.get('seconds', '')), 'yes' if report.get('synthetic') else 'no']
        cells = ''.join(f'<td>{html.escape(v)}</td>' for v in values)
        body.append(f'<tr data-status="{html.escape(status)}">{cells}<td>{link}</td></tr>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compiler Verification Lab</title><style>
:root{font-family:Segoe UI,system-ui,sans-serif;color:#dce6ef;background:#101822}body{max-width:1250px;margin:0 auto;padding:40px 24px}
h1{font-size:34px;margin-bottom:8px}p{color:#adc0d0;line-height:1.6}.stats{display:flex;gap:16px;flex-wrap:wrap;margin:28px 0}
.stat{background:#1a2938;padding:20px 28px;border-radius:10px}.stat b{display:block;font-size:30px;color:#70e2c2}
input,select{padding:12px;border:1px solid #58728c;background:#1a2938;color:white;border-radius:6px;margin-right:12px}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;margin-top:22px;font-size:14px}th,td{text-align:left;padding:12px;border-bottom:1px solid #304457}
th{color:#91b1ce}tr[data-status=PASS] td:nth-child(5){color:#70e2c2}tr[data-status=WRONG_RESULT] td:nth-child(5){color:#ffa67c}a{color:#89bcff}
details{margin-top:28px}pre{white-space:pre-wrap;overflow-wrap:anywhere}footer{margin-top:32px;color:#91a7bb;font-size:13px}
</style><h1>Compiler Verification Lab</h1><p>Reproducible programs, native compiler execution, and retained evidence. Synthetic faults are explicitly labeled.</p>
<div class="stats">STATS</div><label>Find a case <input id="query" placeholder="Seed, profile, status"></label>
<label>Status <select id="status"><option value="">All</option>OPTIONS</select></label>
<div class="scroll"><table><thead><tr><th>Job</th><th>Seed</th><th>Profile</th><th>Kernel</th><th>Result</th><th>Seconds</th><th>Synthetic</th><th>Artifacts</th></tr></thead><tbody>ROWS</tbody></table></div>
<details><summary>Coverage and result counts</summary><pre>SUMMARY</pre></details>
<footer>PASS means agreement for these specific inputs and settings. Model passes check the harness only. Skips are never counted as passes. No claim of exhaustive verification.</footer>
<script>const q=document.getElementById('query'),s=document.getElementById('status');function filter(){for(const r of document.querySelectorAll('tbody tr'))r.hidden=!(r.textContent.toLowerCase().includes(q.value.toLowerCase())&&(!s.value||r.dataset.status===s.value));}q.oninput=filter;s.onchange=filter;</script></html>'''
    stats = [('Cases', summary['cases']), ('Jobs', len(rows)), ('Native passes', summary['native_passes']), ('Model passes', summary['model_passes'])]
    page = page.replace('STATS', ''.join(f'<div class="stat"><b>{v}</b>{k}</div>' for k, v in stats))
    page = page.replace('OPTIONS', ''.join(f'<option>{html.escape(k)}</option>' for k in counts))
    page = page.replace('ROWS', ''.join(body)).replace('SUMMARY', html.escape(json.dumps(summary, indent=2)))
    (folder / 'index.html').write_text(page, encoding='utf-8')
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary
