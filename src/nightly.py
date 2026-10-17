"""Every night: my lessons from the last days → their recordings → summary PDF by email (with what it cost);
a lesson that wasn't recorded in my group → the same week's lesson from another group; new Moodle files and
homework; homework reminders; NotebookLM (optional); the dashboard.

    python -m src.nightly                     # the real run (GitHub Actions calls this)
    python -m src.nightly --dry-run           # what would be done — no AI, no email
    python -m src.nightly --only "הסתברות" --clip-min 5 --no-email   # a cheap test on one course
"""
from __future__ import annotations

import argparse
import re
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from . import ai, common, dashboard, ledger, mailer, panopto, timetable
from .pdf import markdown_to_pdf
from .tau_login import moodle_session, panopto_session

MD = common.STATE / 'md'


def _key(e: dict) -> str:
    return f"{e['number']}|{e['kind']}|{e['group']}|{e['date']}|{e['time']}"


def _previous(lessons: dict, e: dict) -> str:
    prev = sorted((r for r in lessons.values() if r['course'] == e['course'] and r['kind'] == e['kind']
                   and r.get('md') and r['date'] < e['date']), key=lambda r: r['date'])
    if not prev:
        return ''
    p = common.ROOT / prev[-1]['md']
    return p.read_text(encoding='utf-8')[:1500] if p.exists() else ''


def transcript_for(s, sess: dict, key: str, clip_min: float | None) -> tuple[str, str]:
    """→ (transcript, source) — Panopto captions if they're real Hebrew, else Gemini transcription of the audio."""
    did = sess.get('DeliveryID') or ''
    srt = panopto.srt_text(s, did)
    if srt and panopto.srt_is_good(srt):
        return panopto.srt_to_transcript(srt), 'כתוביות פנופטו'
    with tempfile.TemporaryDirectory() as tmp:
        audio = panopto.audio_file(s, did, Path(tmp) / 'a.mp3', clip_min)
        if not audio:
            raise RuntimeError('no captions and no audio for this recording')
        text, _ = ai.transcribe(audio, key)
    if not panopto.text_is_real(text):                       # don't pay for a summary of noise
        raise RuntimeError('the transcription came back empty / repetitive — not summarizing it')
    return text, 'תמלול Gemini'


def summarize_lesson(s, e: dict, sess: dict, lessons: dict, key: str, clip_min: float | None, from_group: str) -> dict:
    title = re.sub(r'<[^>]+>', '', sess.get('SessionName') or '') or f"{e['kind']} {e['date']}"
    transcript, source = transcript_for(s, sess, key, clip_min)
    md, _ = ai.summarize(e['course'], title, transcript, key, previous=_previous(lessons, e))
    name = f"{e['date']} {e['kind']}" + (f' (מקב׳ {from_group})' if from_group else '')
    course_dir = re.sub(r'[\\/:*?"<>|]+', ' ', e['course']).strip()
    pdf = common.SUMMARIES / course_dir / f'{name}.pdf'
    pdf.parent.mkdir(parents=True, exist_ok=True)
    markdown_to_pdf(md, str(pdf), title=title, course_name=e['course'])
    mdp = MD / course_dir / f'{name}.md'
    mdp.parent.mkdir(parents=True, exist_ok=True)
    mdp.write_text(md, encoding='utf-8')
    rel = lambda p: str(p.relative_to(common.ROOT)).replace('\\', '/')
    return {'pdf': rel(pdf), 'md': rel(mdp), 'source': source, 'title': title, 'cost': ledger.lesson_total(key)}


def run(dry: bool = False, only: str = '', clip_min: float | None = None, email: bool = True) -> int:
    tt = timetable.load()
    if not tt.get('confirmed'):
        print('המערכת עוד לא אושרה (config/timetable.yaml: confirmed: false) — לא מסכם כלום.')
        return 0
    st = common.settings()
    now = common.now()
    events = timetable.fetch()
    lessons = common.load_json('lessons.json', {})
    notes = common.load_json('notified.json', {})
    out_mail = []                                            # (subject, html, attachments)

    if (new := timetable.changes(tt, events)) and notes.get('tt_changes') != new:
        notes['tt_changes'] = new
        out_mail.append(('🗓️ שינוי במערכת השעות באתר האוניברסיטה',
                         '<div dir="rtl"><p>באתר מופיעים שיעורים שלא במערכת שאישרת:</p><ul>'
                         + ''.join(f'<li>{x}</li>' for x in new) + '</ul><p>אם הם שלך — להוסיף ל-config/timetable.yaml.</p></div>', []))

    since = (now - timedelta(days=int(st['lookback_days']))).date().isoformat()
    due = [e for e in timetable.mine(tt, events)
           if since <= e['date'] <= now.date().isoformat() and (not only or only in e['course'])
           and datetime.fromisoformat(f"{e['date']}T{e['time']}") + timedelta(hours=1) <= now]
    s = None
    for e in sorted(due, key=lambda e: (e['date'], e['time'])):
        key = _key(e)
        rec = lessons.get(key) or {k: e[k] for k in ('course', 'number', 'kind', 'group', 'date', 'time')}
        if rec.get('status') in ('done', 'other_group', 'missing'):
            continue
        if ledger.over_cap():
            rec['status'] = 'cap'
            lessons[key] = rec
            if notes.get('cap') != now.strftime('%Y-%m'):
                notes['cap'] = now.strftime('%Y-%m')
                out_mail.append(('⛔ הגעת לתקרה החודשית', f"<div dir='rtl'>העלות החודש ${ledger.month_total():.2f} — "
                                 f"התקרה ${st['monthly_cap_usd']}. עצרתי סיכומים עד החודש הבא (אפשר להעלות ב-config/settings.yaml).</div>", []))
            break
        try:
            s = s or panopto_session()
            folders = panopto.find_folders(s, e['course'], e['number'])
            sess = panopto.recording_for(panopto.search(s, '', folders[e['group']]), e['date'], e['time']) \
                if folders.get(e['group']) else None
            from_group = ''
            if not sess:
                end = datetime.fromisoformat(f"{e['date']}T{e.get('end_time') or e['time']}")
                if (now - end).total_seconds() / 3600 < float(st['missing_after_hours']):
                    rec['status'] = 'waiting'
                    lessons[key] = rec
                    continue
                alt = panopto.same_week_elsewhere({g: panopto.search(s, '', f) for g, f in folders.items()},
                                                  e['group'], e['date'])
                if not alt:
                    rec['status'] = 'missing' if e['date'] <= (now - timedelta(days=2)).date().isoformat() else 'waiting'
                    lessons[key] = rec
                    continue
                from_group, sess = alt
            if dry:
                print(f"[dry-run] {e['course']} {e['kind']} {e['date']} → {sess.get('SessionName')}"
                      + (f' (קב׳ {from_group})' if from_group else ''))
                continue
            rec.update(summarize_lesson(s, e, sess, lessons, key, clip_min, from_group))
            rec['status'] = 'other_group' if from_group else 'done'
            if from_group:
                rec['from_group'] = from_group
            lessons[key] = rec
            common.save_json('lessons.json', lessons)
            note = (f"<p>⚠️ השיעור שלך (קב׳ {e['group']}) לא הוקלט/בוטל — זה הסיכום מקבוצה {from_group}.</p>" if from_group else '')
            out_mail.append((f"📄 סיכום: {e['course']} — {e['kind']} {e['date'][8:10]}/{e['date'][5:7]} (${rec['cost']:.2f})",
                             f"<div dir='rtl'><p><b>{e['course']}</b> — {rec['title']}</p>{note}"
                             f"<p>מקור: {rec['source']} · עלות הסיכום: <b>${rec['cost']:.2f}</b> · החודש עד עכשיו: "
                             f"${ledger.month_total():.2f}</p></div>", [common.ROOT / rec['pdf']]))
        except Exception as ex:
            rec['status'] = 'error'
            rec['error'] = str(ex)[:300]
            lessons[key] = rec
            print(f"⚠️ {e['course']} {e['date']}: {ex}")
            traceback.print_exc()
    common.save_json('lessons.json', lessons)

    new_files = []
    if not dry:
        try:
            from . import moodle
            courses = [{'course': c['course'], 'number': c['number'],
                        'groups': sorted({s['group'] for s in c.get('lessons') or []})}
                       for c in tt.get('courses') or [] if c.get('summarize', True)]
            res = moodle.sync(moodle_session(), courses)
            new_files = res['new_files']
            if new_files:
                hw = [Path(f['path']) for f in new_files if f.get('homework')][:5]
                out_mail.append((f'📂 חדש במודל ({len(new_files)})', "<div dir='rtl'><ul>" + ''.join(
                    f"<li>{'📝' if f.get('homework') else '📄'} {f['course']} — {f['title']}</li>" for f in new_files)
                    + '</ul></div>', hw))
            soon = [a for a in res['assignments'] if a.get('due') and not a.get('submitted')
                    and now <= datetime.fromisoformat(a['due']) <= now + timedelta(hours=48)
                    and notes.get(f"hw|{a['url']}") != a['due']]
            for a in soon:
                notes[f"hw|{a['url']}"] = a['due']
            if soon:
                out_mail.append(('⏰ הגשות ב-48 השעות הקרובות', "<div dir='rtl'><ul>" + ''.join(
                    f"<li><b>{a['course']}</b> — {a['title']} · עד {datetime.fromisoformat(a['due']):%d/%m %H:%M}</li>"
                    for a in soon) + '</ul></div>', []))
        except Exception as ex:
            print(f'⚠️ moodle: {ex}')

    if not dry and __import__('os').getenv('NOTEBOOKLM_STORAGE'):
        try:
            from . import notebooklm
            print(f'NotebookLM: {notebooklm.sync()}')
        except Exception as ex:
            print(f'⚠️ NotebookLM: {ex!r}'[:300])
            if notes.get('nlm_fail') != now.strftime('%G-%V'):
                notes['nlm_fail'] = now.strftime('%G-%V')
                out_mail.append(('📚 NotebookLM לא התחבר מ-GitHub', "<div dir='rtl'>גוגל כנראה ניתק את ההתחברות. "
                                 "אפשר להריץ במחשב: <code>python -m src.notebooklm</code> (מעלה את כל מה שחדש).</div>", []))

    html = dashboard.build(new_files)
    common.save_json('notified.json', notes)
    if email and not dry:
        for subject, body, att in out_mail:
            mailer.send(subject, body + '<hr>' + html, att)
    print(f'done: {len(out_mail)} emails, month ${ledger.month_total():.2f}')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--clip-min', type=float)
    ap.add_argument('--no-email', action='store_true')
    a = ap.parse_args()
    raise SystemExit(run(a.dry_run, a.only, a.clip_min, not a.no_email))
