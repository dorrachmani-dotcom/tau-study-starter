"""On the 1st of the month: last month's bill — how many summaries / transcriptions, and what each kind cost."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from . import common, dashboard, ledger, mailer

OPS = {'summary': 'סיכומים', 'transcribe': 'תמלולים'}


def report(month: str | None = None) -> tuple[str, str]:
    if not month:
        first = common.now().replace(day=1)
        month = (first - timedelta(days=1)).strftime('%Y-%m')
    rows = [r for r in common.load_json('ledger.json', []) if r['ts'].startswith(month)]
    by = defaultdict(lambda: [0, 0.0])
    for r in rows:
        by[r['op']][0] += 1
        by[r['op']][1] += r['cost']
    total = sum(v[1] for v in by.values())
    lines = ''.join(f"<tr><td>{OPS.get(op, op)}</td><td>{n}</td><td>${c:.2f}</td></tr>" for op, (n, c) in by.items())
    html = (f"<div dir='rtl'><h2>📊 עלות חודשית — {month[5:]}/{month[:4]}</h2>"
            f"<table border='0' cellpadding='6'><tr><th>מה</th><th>כמה</th><th>עלות</th></tr>{lines}</table>"
            f"<p><b>סה״כ: ${total:.2f}</b> (תקרה ${common.settings()['monthly_cap_usd']})</p></div>")
    return f'📊 עלות {month[5:]}/{month[:4]}: ${total:.2f}', html


if __name__ == '__main__':
    subject, html = report()
    mailer.send(subject, html + '<hr>' + dashboard.build())
    print(subject)
