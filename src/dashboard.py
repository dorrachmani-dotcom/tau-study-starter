"""The dashboard: this week's lessons and their summaries, homework due, new Moodle files, and the month's cost.
Written to docs/dashboard.html (open it from the repo) and sent inside the emails. Plain HTML + CSS, RTL."""
from __future__ import annotations

import html
from datetime import datetime, timedelta

from . import common, ledger

STATUS = {'done': ('✅', 'סוכם'), 'other_group': ('🔁', 'מקבוצה אחרת'), 'waiting': ('⏳', 'מחכה להקלטה'),
          'missing': ('❌', 'לא הוקלט'), 'cap': ('⛔', 'עצר — תקרה'), 'error': ('⚠️', 'תקלה')}

CSS = """
:root{--bg:#f6f7fb;--card:#fff;--ink:#1d2433;--muted:#6b7385;--line:#e6e8ef;--accent:#3b5bdb;--ok:#2b8a3e;--warn:#e67700;--bad:#c92a2a}
@media (prefers-color-scheme:dark){:root{--bg:#12151c;--card:#1b202b;--ink:#e8ebf2;--muted:#9aa3b5;--line:#2a3140;--accent:#7c95ff;--ok:#69db7c;--warn:#ffa94d;--bad:#ff8787}}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Heebo,Arial,sans-serif;direction:rtl}
.wrap{max-width:760px;margin:0 auto;padding:20px 16px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.card h2{font-size:16px;margin:0 0 10px}
.kpis{display:flex;gap:10px;flex-wrap:wrap}.kpi{flex:1;min-width:140px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.kpi b{display:block;font-size:22px}.kpi span{color:var(--muted);font-size:12px}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:7px 4px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px}.muted{color:var(--muted)}.late{color:var(--bad);font-weight:600}.soon{color:var(--warn);font-weight:600}
"""


def _e(s) -> str:
    return html.escape(str(s or ''))


def build(new_files: list[dict] | None = None) -> str:
    st = common.settings()
    now = common.now()
    lessons = common.load_json('lessons.json', {})
    rows_l = sorted(lessons.values(), key=lambda r: (r['date'], r['time']), reverse=True)
    week_ago = (now - timedelta(days=7)).date().isoformat()
    recent = [r for r in rows_l if r['date'] >= week_ago] or rows_l[:8]
    spent, cap = ledger.month_total(), float(st['monthly_cap_usd'])
    done_month = sum(1 for r in rows_l if r['date'][:7] == now.strftime('%Y-%m') and r['status'] in ('done', 'other_group'))
    assigns = [a for a in common.load_json('assignments.json', []) if a.get('due')]
    upcoming = sorted([a for a in assigns if a['due'] >= (now - timedelta(days=1)).isoformat()], key=lambda a: a['due'])[:10]

    def lesson_row(r):
        icon, word = STATUS.get(r['status'], ('•', r['status']))
        note = f" (קב׳ {_e(r.get('from_group'))})" if r['status'] == 'other_group' else ''
        cost = f"${r['cost']:.2f}" if r.get('cost') else ''
        return (f"<tr><td>{_e(r['date'][8:10])}/{_e(r['date'][5:7])} {_e(r['time'])}</td><td>{_e(r['course'])}</td>"
                f"<td>{_e(r['kind'])}</td><td>{icon} {word}{note}</td><td class='muted'>{cost}</td></tr>")

    def due_row(a):
        due = datetime.fromisoformat(a['due'])
        left = (due - now).days
        cls = 'late' if due < now and not a.get('submitted') else ('soon' if left <= 3 and not a.get('submitted') else '')
        state = '✅ הוגש' if a.get('submitted') else (f'בעוד {left} ימים' if due >= now else 'עבר המועד')
        return (f"<tr><td>{_e(a['course'])}</td><td>{_e(a['title'])}</td><td>{due:%d/%m %H:%M}</td>"
                f"<td class='{cls}'>{state}</td></tr>")

    files = new_files or []
    pct = min(100, int(100 * spent / cap)) if cap else 0
    parts = [
        f"<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>הלימודים שלי</title><style>{CSS}</style></head><body><div class='wrap'>",
        f"<h1>📚 הלימודים שלי</h1><div class='sub'>עודכן {now:%d/%m/%Y %H:%M}</div>",
        "<div class='kpis'>",
        f"<div class='kpi'><b>{done_month}</b><span>סיכומים החודש</span></div>",
        f"<div class='kpi'><b>{len([a for a in upcoming if not a.get('submitted')])}</b><span>מטלות פתוחות</span></div>",
        f"<div class='kpi'><b>${spent:.2f}</b><span>עלות החודש (תקרה ${cap:.0f})</span><div class='bar'><i style='width:{pct}%'></i></div></div>",
        "</div>",
        "<div class='card'><h2>🗓️ השיעורים האחרונים</h2><table><tr><th>מתי</th><th>קורס</th><th>סוג</th><th>מצב</th><th>עלות</th></tr>"
        + (''.join(lesson_row(r) for r in recent) or "<tr><td colspan='5' class='muted'>עוד אין</td></tr>") + "</table></div>",
        "<div class='card'><h2>📝 מטלות</h2><table><tr><th>קורס</th><th>מטלה</th><th>הגשה</th><th>מצב</th></tr>"
        + (''.join(due_row(a) for a in upcoming) or "<tr><td colspan='4' class='muted'>אין מטלות פתוחות</td></tr>") + "</table></div>",
    ]
    if files:
        parts.append("<div class='card'><h2>📂 חדש במודל</h2><table>" + ''.join(
            f"<tr><td>{'📝' if f.get('homework') else '📄'}</td><td>{_e(f['course'])}</td><td>{_e(f['title'])}</td></tr>"
            for f in files[:30]) + "</table></div>")
    parts.append("<div class='sub'>הסיכומים נמצאים בתיקייה summaries/ והחומרים ב-materials/ ב-repo.</div></div></body></html>")
    out = ''.join(parts)
    common.DOCS.mkdir(parents=True, exist_ok=True)
    (common.DOCS / 'dashboard.html').write_text(out, encoding='utf-8')
    return out
