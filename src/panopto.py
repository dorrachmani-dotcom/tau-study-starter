"""Panopto: find my group's folder (and the other groups'), find a lesson's recording, get its transcript.

TAU folder names carry "(<8-digit course number><2-digit group>-<year>-<semester>)", e.g.
"(0368200201-2026-1) הסתברות וסטטיסטיקה" — that's how my group's folder and the other groups' are found.
Never filter recordings by a keyword in their title (a friend's filter dropped every lecture when the
titles changed to "שיעור N"); match by folder + date + time instead.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import common
from .tau_login import PANOPTO

DOTNET_DATE = re.compile(r'/Date\((-?\d+)\)/')


def parse_date(raw: str) -> datetime | None:
    """Panopto start time (/Date(ms)/ or ISO, UTC) → Israel local time."""
    if not raw:
        return None
    m = DOTNET_DATE.search(raw)
    try:
        dt = (datetime.fromtimestamp(int(m.group(1)) / 1000, timezone.utc).replace(tzinfo=None) if m
              else datetime.fromisoformat(raw[:19]))
    except ValueError:
        return None
    return common.to_israel(dt)


def search(s, query: str = '', folder_id: str | None = None) -> list[dict]:
    payload = {'queryParameters': {'query': query, 'sortColumn': 1, 'sortAscending': False, 'maxResults': 100,
                                   'page': 0, 'startDate': None, 'endDate': None, 'folderID': folder_id,
                                   'bookmarked': False, 'sessionListOnly': True, 'isSharedWithMe': False}}
    r = s.post(f'{PANOPTO}/Panopto/Services/Data.svc/GetSessions', json=payload, timeout=30)
    r.raise_for_status()
    return (r.json().get('d') or {}).get('Results') or []


def group_folders(sessions: list[dict], number8: str, t: str) -> dict[str, str]:
    """{group: folder id} for every folder of this course in this semester (from search results)."""
    out = {}
    for s in sessions:
        name = re.sub(r'<[^>]+>', '', s.get('FolderName', '') or '')
        m = re.search(re.escape(number8) + r'(\d{2})-' + re.escape(t), name)
        if m and s.get('FolderID'):
            out.setdefault(m.group(1), s['FolderID'])
    return out


def find_folders(s, course: str, number8: str) -> dict[str, str]:
    """Search Panopto by the course name and by its number → {group: folder id}. Cached in state/folders.json."""
    cache = common.load_json('folders.json', {})
    t = common.term()
    key = f'{number8}-{t}'
    if cache.get(key):
        return cache[key]
    found = {}
    for q in (course, number8, number8.lstrip('0')):
        try:
            found.update({g: f for g, f in group_folders(search(s, q), number8, t).items() if g not in found})
        except Exception as e:
            print(f'  ⚠️ panopto search "{q}": {e}')
    if found:
        cache[key] = found
        common.save_json('folders.json', cache)
    return found


def long_enough(s: dict, min_sec: int = 300) -> bool:
    """Empty / test recordings (0–5 min) aren't lessons — transcribing one produced 60k tokens of "אוקיי"."""
    if s.get('Duration') in (None, ''):
        return True                                          # unknown length — don't drop it
    try:
        return float(s['Duration']) >= min_sec
    except (TypeError, ValueError):
        return True


def text_is_real(text: str, min_chars: int = 800) -> bool:
    """A transcript worth summarizing: long enough and not one phrase on repeat."""
    words = (text or '').split()
    if len(text or '') < min_chars or len(words) < 100:
        return False
    return Counter(words).most_common(1)[0][1] / len(words) < 0.25


def recording_for(sessions: list[dict], day: str, hhmm: str, slack_min: int = 90) -> dict | None:
    """The recording of the lesson that started at day+hhmm (Israel time), ±slack."""
    want = datetime.fromisoformat(f'{day}T{hhmm or "00:00"}')
    best, gap = None, None
    for s in sessions:
        if not long_enough(s):
            continue
        st = parse_date(s.get('StartTime', ''))
        if not st or st.date().isoformat() != day:
            continue
        g = abs((st - want).total_seconds()) / 60
        if (not hhmm or g <= slack_min) and (gap is None or g < gap):
            best, gap = s, g
    return best


def same_week_elsewhere(per_group: dict[str, list[dict]], mine: str, day: str) -> tuple[str, dict] | None:
    """My group's lesson is missing → the same week's recording from another group (closest day)."""
    d0 = datetime.fromisoformat(day)
    week0 = d0 - timedelta(days=(d0.weekday() + 1) % 7)          # Sunday-based week
    best = None
    for g, sessions in per_group.items():
        if g == mine:
            continue
        for s in sessions:
            st = parse_date(s.get('StartTime', ''))
            if st and long_enough(s) and week0 <= st < week0 + timedelta(days=7):
                gap = abs((st.date() - d0.date()).days)
                if best is None or gap < best[0]:
                    best = (gap, g, s)
    return (best[1], best[2]) if best else None


def srt_text(s, delivery_id: str) -> str:
    r = s.get(f'{PANOPTO}/Panopto/Pages/Transcription/GenerateSRT.ashx', params={'id': delivery_id, 'language': 0},
              timeout=60)
    return r.text if r.status_code == 200 and '-->' in r.text else ''


def srt_is_good(srt: str) -> bool:
    """Panopto's captions are sometimes gibberish (Cyrillic instead of Hebrew, or one line repeated)."""
    clean = re.sub(r'^\d+\s*$', '', srt, flags=re.M)
    clean = re.sub(r'^\d{2}:\d{2}:\d{2}[^\n]*$', '', clean, flags=re.M)
    lines = [l.strip() for l in clean.split('\n') if l.strip()]
    speech = ' '.join(lines)
    if len(speech) < 500:
        return False
    alpha = sum(c.isalpha() for c in speech)
    heb = sum('א' <= c <= 'ת' for c in speech)
    if alpha > 200 and heb / alpha < 0.20:
        return False
    return not lines or Counter(lines).most_common(1)[0][1] / len(lines) <= 0.40


def srt_to_transcript(srt: str) -> str:
    """'[HH:MM:SS] text' lines."""
    out, stamp = [], ''
    for line in srt.splitlines():
        line = line.strip()
        if '-->' in line:
            stamp = line.split(',')[0].split('.')[0]
        elif line and not line.isdigit():
            out.append(f'[{stamp}] {line}')
    return '\n'.join(out)


def media_url(s, delivery_id: str) -> str | None:
    """A direct MP4 if there is one, else the HLS stream (ffmpeg reads both)."""
    from xml.etree import ElementTree as ET
    r = s.get(f'{PANOPTO}/Panopto/Pages/Viewer/DeliveryInfo.aspx', params={'deliveryId': delivery_id, 'isEmbed': 'true'},
              timeout=30)
    if r.status_code != 200:
        return None
    sess_file = stream_file = hls = None
    try:
        for el in ET.fromstring(r.text).iter():
            tag, text = el.tag.split('}')[-1], (el.text or '').strip()
            if tag == 'SessionFileId' and not sess_file:
                sess_file = text
            elif tag == 'StreamFileId' and not stream_file:
                stream_file = text
            elif tag == 'StreamUrl' and not hls and text.startswith('http'):
                hls = text
    except ET.ParseError:
        return None
    if sess_file and stream_file:
        mp4 = f'https://d2hpwsdp0ihr0w.cloudfront.net/sessions/{sess_file}/{delivery_id}-{stream_file}.mp4'
        try:
            if s.head(mp4, timeout=15, allow_redirects=True).status_code == 200:
                return mp4
        except Exception:
            pass
    return hls


def audio_file(s, delivery_id: str, out: Path, clip_min: float | None = None) -> Path | None:
    """The lecture's audio as a small mono mp3 (ffmpeg). clip_min: only the first N minutes (for testing)."""
    url = media_url(s, delivery_id)
    if not url:
        return None
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', url, '-vn', '-ac', '1', '-ar', '16000', '-b:a', '32k']
    if clip_min:
        cmd += ['-t', str(int(clip_min * 60))]
    subprocess.run(cmd + [str(out)], check=True, timeout=3600)
    return out if out.exists() and out.stat().st_size > 10000 else None
