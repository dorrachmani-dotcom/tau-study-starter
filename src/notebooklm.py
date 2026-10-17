"""Optional: every summary, Moodle file and homework into one NotebookLM notebook per course (free, my own Google
account) — then I ask NotebookLM questions about the course.

NotebookLM has no official API; this uses the notebooklm-py library with a normal Google sign-in:
  1. On my computer, once: `pip install notebooklm-py` → `notebooklm login` (a browser opens, I sign in).
  2. Either run `python -m src.notebooklm` on my computer (uploads everything new), or put the contents of
     ~/.notebooklm/profiles/default/storage_state.json in the GitHub secret NOTEBOOKLM_STORAGE and the nightly run
     will try. Google may drop a sign-in that's used from GitHub's ever-changing servers — then the run says so, and
     the computer route keeps working.
state/notebooklm.json: {course: {notebook_id, uploaded: [paths]}}
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from . import common

TYPES = {'.pdf', '.docx', '.txt', '.md', '.pptx'}


def _storage_path() -> str | None:
    if os.getenv('NOTEBOOKLM_STORAGE'):                       # GitHub: the secret's content → a temp file
        p = Path(tempfile.gettempdir()) / 'nlm_storage_state.json'
        p.write_text(os.environ['NOTEBOOKLM_STORAGE'], encoding='utf-8')
        return str(p)
    return None                                             # my computer: the library's own login


def pending() -> dict[str, list[Path]]:
    """{course folder: files not uploaded yet} — summaries/<course>/ and materials/<course>/ (incl. מטלות/)."""
    st = common.load_json('notebooklm.json', {})
    out: dict[str, list[Path]] = {}
    for base in (common.SUMMARIES, common.ROOT / 'materials'):
        if not base.exists():
            continue
        for course_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            done = set((st.get(course_dir.name) or {}).get('uploaded') or [])
            for f in sorted(course_dir.rglob('*')):
                rel = str(f.relative_to(common.ROOT)).replace('\\', '/')
                if f.is_file() and f.suffix.lower() in TYPES and rel not in done:
                    out.setdefault(course_dir.name, []).append(f)
    return out


async def _sync(todo: dict[str, list[Path]]) -> dict[str, int]:
    from notebooklm import NotebookLMClient
    st = common.load_json('notebooklm.json', {})
    added: dict[str, int] = {}
    async with await NotebookLMClient.from_storage(path=_storage_path()) as c:
        for course, files in todo.items():
            rec = st.setdefault(course, {'notebook_id': '', 'uploaded': []})
            if not rec['notebook_id']:
                nb = await c.notebooks.create(f'📚 {course}')
                rec['notebook_id'] = getattr(nb, 'notebook_id', None) or getattr(nb, 'id', None)
            for f in files:
                try:
                    await c.sources.add_file(rec['notebook_id'], str(f), wait=True, wait_timeout=180, title=f.stem[:90])
                except Exception as e:
                    print(f'  ⚠️ NotebookLM {f.name}: {e!r}'[:200])
                    continue
                rec['uploaded'].append(str(f.relative_to(common.ROOT)).replace('\\', '/'))
                added[course] = added.get(course, 0) + 1
                common.save_json('notebooklm.json', st)
    return added


def sync() -> dict[str, int]:
    todo = pending()
    if not todo:
        return {}
    return asyncio.run(_sync(todo))


if __name__ == '__main__':
    res = sync()
    print('\n'.join(f'{k}: +{v}' for k, v in res.items()) or 'אין חדש להעלות.')
