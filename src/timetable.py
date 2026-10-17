"""My timetable from the university's personal area (my.tau) — read it, propose it, and only after I confirm it does
anything run. `python -m src.timetable --propose` writes config/timetable.yaml with confirmed: false.

Each lesson on my.tau carries: course, course number (8 digits), group, kind (שיעור/תרגיל), date, time, room.
"""
from __future__ import annotations

import re
import sys
from datetime import date

import yaml

from . import common
from .tau_login import MOODLE, fill_nidp

HOME = 'https://my.tau.ac.il/TAU_Student/'
DAYS = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']
KINDS = ('שיעור', 'תרגיל')


def _events_from(obj, out: list) -> None:
    if isinstance(obj, dict):
        if 'start' in obj and obj.get('title'):
            out.append(obj)
            return
        for v in obj.values():
            _events_from(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _events_from(v, out)


def _norm(e: dict) -> dict:
    title, start = (e.get('title') or '').strip(), (e.get('start') or '').strip()
    hhmm = ''
    if m := re.search(r'שעת התחלה\s*(\d{1,2}:\d{2})', title):
        hhmm = m.group(1).zfill(5)
    elif re.search(r' \d{2}:\d{2}', start) and not start.endswith('00:00:00'):
        hhmm = start[11:16]
    room = (e.get('Room') or '').strip()
    return {'course': re.sub(r'\s*-\s*שעת התחלה.*$', '', title).strip(), 'date': start[:10], 'time': hhmm,
            'end_time': (e.get('end') or '')[11:16] if re.search(r' \d{2}:\d{2}', e.get('end') or '') else '',
            'kind': (e.get('LessonTypeHeb') or e.get('TagDescHeb') or '').strip(),
            'is_exam': e.get('EventType') == 'exam' or 'בחינה' in (e.get('LessonTypeHeb') or ''),
            'building': (e.get('BuildingNameHeb') or '').strip(), 'room': '' if room.strip('0') == '' else room,
            'number': e.get('CourseNumber') or '', 'group': (e.get('Group') or '').strip()}


def fetch(timeout_ms: int = 40000) -> list[dict]:
    """Log in (SSO through Moodle) and read the full calendar the my.tau page itself loads. Raises on failure."""
    from playwright.sync_api import sync_playwright
    bodies: list = []

    def on_resp(r):
        if 'screenservices' in r.url and ('Calendar' in r.url or 'Schedules' in r.url):
            try:
                bodies.append(r.json())
            except Exception:
                pass

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            page = b.new_context(locale='he-IL').new_page()
            page.on('response', on_resp)
            page.goto(f'{MOODLE}/login/index.php')
            page.wait_for_load_state('networkidle')
            for sel in ('a[href*="shibboleth"]', 'a[href*="saml"]', 'a[href*="nidp"]', 'text=SSO'):
                try:
                    page.click(sel, timeout=2500)
                    break
                except Exception:
                    continue
            page.wait_for_load_state('networkidle')
            fill_nidp(page)
            page.goto(HOME, timeout=timeout_ms)
            page.wait_for_load_state('networkidle', timeout=timeout_ms)
            try:
                page.get_by_text('Got it').first.click(timeout=3000)
            except Exception:
                pass
            page.get_by_text('ליומן המלא').first.click(timeout=15000)
            page.wait_for_load_state('networkidle', timeout=timeout_ms)
            page.wait_for_timeout(3000)
        finally:
            b.close()
    raw: list = []
    for body in bodies:
        _events_from(body, raw)
    seen, events = set(), []
    for e in map(_norm, raw):
        k = (e['course'], e['date'], e['time'], e['group'])
        if e['date'] and k not in seen:
            seen.add(k)
            events.append(e)
    if not events:
        raise RuntimeError('my.tau returned an empty calendar')
    common.save_json('tau_calendar.json', {'fetched_at': common.now().isoformat(timespec='seconds'), 'events': events})
    return sorted(events, key=lambda e: (e['date'], e['time']))


def lessons(events: list[dict]) -> list[dict]:
    return [e for e in events if not e['is_exam'] and e['time'] and e['kind'] in KINDS and e['number'].strip('0')]


def propose(events: list[dict]) -> dict:
    """Weekly slots per course, for me to confirm."""
    courses: dict[str, dict] = {}
    for e in lessons(events):
        c = courses.setdefault(e['number'], {'course': e['course'], 'number': e['number'], 'summarize': True, 'lessons': []})
        slot = {'kind': e['kind'], 'group': e['group'], 'day': DAYS[date.fromisoformat(e['date']).weekday()],
                'time': e['time'], 'place': ' '.join(x for x in (e['building'], e['room']) if x)}
        if not any(s['kind'] == slot['kind'] and s['group'] == slot['group'] and s['day'] == slot['day']
                   and s['time'] == slot['time'] for s in c['lessons']):
            c['lessons'].append(slot)
    return {'confirmed': False, 'courses': list(courses.values())}


def load() -> dict:
    p = common.CONFIG / 'timetable.yaml'
    return (yaml.safe_load(p.read_text(encoding='utf-8')) or {}) if p.exists() else {}


def save(tt: dict) -> None:
    common.CONFIG.mkdir(parents=True, exist_ok=True)
    (common.CONFIG / 'timetable.yaml').write_text(
        '# המערכת שלי — לבדוק, לתקן אם צריך, ולשנות confirmed ל-true. summarize: false = לא לסכם את הקורס הזה.\n'
        + yaml.safe_dump(tt, allow_unicode=True, sort_keys=False), encoding='utf-8')


def text(tt: dict) -> str:
    out = []
    for c in tt.get('courses') or []:
        out.append(f"{'✅' if c.get('summarize', True) else '⏸️'} {c['course']} ({c['number']})")
        out += [f"   • {s['kind']} קב׳ {s['group']} — יום {s['day']} {s['time']}" + (f" · {s['place']}" if s.get('place') else '')
                for s in c.get('lessons') or []]
    return '\n'.join(out)


def mine(tt: dict, events: list[dict]) -> list[dict]:
    """The dated lessons that are mine (confirmed course + kind + group)."""
    want = {(c['number'], s['kind'], s['group']) for c in tt.get('courses') or [] if c.get('summarize', True)
            for s in c.get('lessons') or []}
    return [e for e in lessons(events) if (e['number'], e['kind'], e['group']) in want]


def changes(tt: dict, events: list[dict]) -> list[str]:
    """Lessons on my.tau that the confirmed timetable doesn't know (a new group, a new course) — to tell me."""
    known = {(c['number'], s['kind'], s['group']) for c in tt.get('courses') or [] for s in c.get('lessons') or []}
    new = {(e['course'], e['number'], e['kind'], e['group']) for e in lessons(events)
           if (e['number'], e['kind'], e['group']) not in known}
    return [f'{c} — {k} קב׳ {g}' for c, _, k, g in sorted(new)]


if __name__ == '__main__':
    if '--propose' in sys.argv:
        tt = propose(fetch())
        save(tt)
        print(text(tt))
        print('\nנשמר ב-config/timetable.yaml (confirmed: false). לבדוק ולאשר.')
    else:
        print(text(load()))
