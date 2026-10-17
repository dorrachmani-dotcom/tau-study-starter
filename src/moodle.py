"""Moodle: my courses (found on /my/ by course number + group), every file on their pages, and the assignments
(due date, submitted or not, the assignment's own file). New files land in materials/<course>/ — for the email,
the dashboard and NotebookLM. No AI here, nothing paid.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import common
from .tau_login import MOODLE

MATERIALS = common.ROOT / 'materials'
HE_MONTHS = {'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'מרס': 3, 'אפריל': 4, 'מאי': 5, 'יוני': 6, 'יולי': 7, 'אוגוסט': 8,
             'ספטמבר': 9, 'אוקטובר': 10, 'נובמבר': 11, 'דצמבר': 12}
DATE_RX = [re.compile(r'(\d{1,2})\s+(' + '|'.join(HE_MONTHS) + r')\s+(\d{4}),?\s*(\d{1,2}):(\d{2})'),
           re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4}),?\s*(\d{1,2}):(\d{2})')]
HW_RX = re.compile(r'תרגיל|מטלה|HW|homework|הגשה|גיליון', re.I)
FILE_EXT = {'.pdf', '.pptx', '.docx', '.doc', '.xlsx', '.zip', '.py', '.java', '.ipynb', '.txt', '.png', '.jpg'}


def parse_he_date(text: str) -> str | None:
    for i, rx in enumerate(DATE_RX):
        m = rx.search(text or '')
        if not m:
            continue
        d, mo, y, h, mi = m.groups()
        mo = HE_MONTHS.get(mo) if i == 0 else int(mo)
        try:
            return datetime(int(y), int(mo), int(d), int(h), int(mi)).isoformat(timespec='minutes')
        except (TypeError, ValueError):
            continue
    return None


def enrolled_ids(s) -> set[str]:
    """The course ids Moodle lists for me — the same AJAX call the /my/ page makes (its HTML has no course links)."""
    html = s.get(f'{MOODLE}/my/', timeout=30).text
    m = re.search(r'"sesskey":"([^"]+)"', html)
    if not m:
        return set()
    body = [{'index': 0, 'methodname': 'core_course_get_enrolled_courses_by_timeline_classification',
             'args': {'offset': 0, 'limit': 0, 'classification': 'all', 'sort': 'fullname'}}]
    try:
        r = s.post(f'{MOODLE}/lib/ajax/service.php?sesskey={m.group(1)}&info=core_course_get_enrolled_courses_by_timeline_classification',
                   json=body, timeout=30).json()[0]
        return {str(c['id']) for c in ((r.get('data') or {}).get('courses') or [])}
    except Exception as e:
        print(f'  ⚠️ moodle course list: {e}')
        return set()


def _opens(s, cid: str, number8: str) -> bool:
    """A course page that exists and is this course (a closed / unknown id shows an error page)."""
    try:
        h = s.get(f'{MOODLE}/course/view.php?id={cid}', timeout=30).text
    except Exception:
        return False
    t = re.search(r'<title>(.*?)</title>', h, re.S)
    return bool(t) and number8 in t.group(1)


def my_course_ids(s, courses: list[dict]) -> dict[str, list[str]]:
    """{8-digit course number: [moodle ids]}. Moodle ids are the course number (no leading zeros) + 2-digit group:
    the ones Moodle lists for me, plus my timetable's groups if their page opens (a course not listed yet)."""
    listed = enrolled_ids(s)
    out: dict[str, list[str]] = {}
    for c in courses:
        n, short = c['number'], c['number'].lstrip('0')
        ids = {i for i in listed if i.startswith(short) and len(i) - len(short) == 2}
        for g in c.get('groups') or []:
            cid = f'{short}{g}'
            if cid not in ids and _opens(s, cid, n):
                ids.add(cid)
        out[n] = sorted(ids)
    return out


def _clean(raw: str) -> str:
    t = re.sub(r'<[^>]+>', ' ', raw)
    t = re.sub(r'\s+', ' ', t).strip()
    return re.sub(r'\s+(קובץ|File|PDF|מטלה|Assignment)$', '', t, flags=re.I)


def course_page(s, cid: str) -> tuple[list[dict], list[dict]]:
    """→ (files [{title, url, id}], assignments [{title, url, id}]) on one Moodle course page."""
    html = s.get(f'{MOODLE}/course/view.php?id={cid}', timeout=30).text
    files, assigns, seen = [], [], set()
    for href, rid, raw in re.findall(r'href="(https?://moodle\.tau\.ac\.il/mod/resource/view\.php\?id=(\d+))[^"]*"[^>]*>(.*?)</a>',
                                     html, re.S):
        if rid not in seen:
            seen.add(rid)
            files.append({'title': _clean(raw) or f'file {rid}', 'url': href, 'id': rid})
    for href, aid, raw in re.findall(r'href="(https?://moodle\.tau\.ac\.il/mod/assign/view\.php\?id=(\d+))[^"]*"[^>]*>(.*?)</a>',
                                     html, re.S):
        if aid not in seen:
            seen.add(aid)
            assigns.append({'title': _clean(raw), 'url': href, 'id': aid})
    return files, assigns


def assignment_details(s, url: str) -> dict:
    html = s.get(url, timeout=30).text
    due = None
    for label in ('מסתיים', 'Due date', 'תאריך הגשה', 'Cut-off date'):
        m = re.search(re.escape(label) + r'[:\s<>/td"\']*(.+?)(?:</td>|<br|</p|</div|$)', html, re.S)
        if m and (due := parse_he_date(re.sub(r'<[^>]+>', ' ', m.group(1))[:200])):
            break
    f = re.search(r'href="(https?://moodle\.tau\.ac\.il/pluginfile\.php/[^"]+/mod_assign/introattachment/[^"]+)"', html)
    return {'due': due, 'submitted': any(x in html for x in ('הוגש להערכה', 'Submitted for grading', 'submissionstatussubmitted')),
            'file_url': f.group(1) if f else None}


def _safe(name: str) -> str:
    return (re.sub(r'[^\w\s\-.֐-׿]', '', name).strip() or 'file')[:80]


def download(s, url: str, dest_dir: Path, title: str) -> Path | None:
    """A resource page → its real file (pluginfile.php) → dest_dir/<title><ext>."""
    real = url
    if '/mod/resource/' in url:
        page = s.get(url, timeout=30, allow_redirects=True)
        if 'pluginfile.php' in page.url:                    # Moodle sometimes redirects straight to the file
            real = page.url
        else:
            m = re.search(r'href="(https?://[^"]*pluginfile\.php[^"]+)"', page.text)
            if not m:
                return None
            real = m.group(1)
    r = s.get(real, timeout=120, allow_redirects=True)
    if r.status_code != 200 or not r.content:
        return None
    ext = Path(real.split('?')[0]).suffix.lower()
    if ext not in FILE_EXT:
        ext = '.pdf' if 'pdf' in r.headers.get('Content-Type', '') else (ext or '.bin')
    dest_dir.mkdir(parents=True, exist_ok=True)
    p = dest_dir / f'{_safe(title)}{ext}'
    p.write_bytes(r.content)
    return p


def sync(s, courses: list[dict]) -> dict:
    """courses: [{'course', 'number', 'groups'}]. Downloads files not seen before; refreshes the assignments.
    → {'new_files': [{course, title, path}], 'assignments': [...]}"""
    seen = common.load_json('moodle_seen.json', {})
    ids = my_course_ids(s, courses)
    new_files, assignments = [], []
    for c in courses:
        for cid in ids.get(c['number'], []):
            try:
                files, assigns = course_page(s, cid)
            except Exception as e:
                print(f"  ⚠️ moodle {c['course']} ({cid}): {e}")
                continue
            for f in files:
                if f['id'] in seen:
                    continue
                try:
                    p = download(s, f['url'], MATERIALS / _safe(c['course']), f['title'])
                except Exception as e:
                    print(f"  ⚠️ {f['title']}: {e}")
                    continue
                seen[f['id']] = {'title': f['title'], 'path': str(p.relative_to(common.ROOT)) if p else ''}
                if p:
                    new_files.append({'course': c['course'], 'title': f['title'], 'path': str(p),
                                      'homework': bool(HW_RX.search(f['title']))})
            for a in assigns:
                try:
                    d = assignment_details(s, a['url'])
                except Exception:
                    d = {}
                rec = {'course': c['course'], 'title': a['title'], 'url': a['url'], **d}
                if d.get('file_url') and f"a{a['id']}" not in seen:
                    p = download(s, d['file_url'], MATERIALS / _safe(c['course']) / 'מטלות', a['title'])
                    seen[f"a{a['id']}"] = {'title': a['title'], 'path': str(p.relative_to(common.ROOT)) if p else ''}
                    if p:
                        new_files.append({'course': c['course'], 'title': a['title'], 'path': str(p), 'homework': True})
                assignments.append(rec)
    common.save_json('moodle_seen.json', seen)
    common.save_json('assignments.json', assignments)
    return {'new_files': new_files, 'assignments': assignments}
