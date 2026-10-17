"""Gemini: the lecture summary (the same prompt a friend's system uses — prompts/summary.md) and, when Panopto has
no usable captions, transcribing the audio. Every call goes through the ledger with its real cost."""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import common, ledger

PROMPT = common.ROOT / 'prompts' / 'summary.md'


def _client():
    import google.genai as genai
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GEMINI_API_KEY is not set')
    return genai.Client(api_key=key)


def _config(model: str, max_tokens: int, low_thinking: bool = False):
    from google.genai import types as T
    kw = dict(max_output_tokens=max_tokens, temperature=0.3)
    if low_thinking:
        kw['thinking_config'] = T.ThinkingConfig(thinking_level='low')
    elif 'flash' in model:
        kw['thinking_config'] = T.ThinkingConfig(thinking_budget=0)   # flash: no thinking — faster, cheaper
    return T.GenerateContentConfig(**kw)


def summarize(course: str, title: str, transcript: str, lesson: str, previous: str = '', slides: str = '') -> tuple[str, float]:
    """→ (markdown, cost)."""
    model = common.settings()['summary_model']
    prompt = (PROMPT.read_text(encoding='utf-8').replace('<<COURSE>>', course).replace('<<TITLE>>', title)
              .replace('<<TRANSCRIPT>>', transcript[:400000]).replace('<<SLIDES>>', slides or '(אין)')
              .replace('<<PREVIOUS>>', f'## תזכורת — מה נלמד בשיעור הקודם\n{previous}\n' if previous else ''))
    last = None
    client = _client()                                       # keep a reference — a dropped client closes mid-call
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=_config(model, 16000))
            c = ledger.log(resp, model, 'summary', lesson)
            text = (resp.text or '').strip()
            if len(text) < 500:
                raise RuntimeError(f'a too-short answer ({len(text)} chars)')
            return text, c
        except Exception as e:
            last = e
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f'summary failed: {last}')


TRANSCRIBE = ('תמלל את ההקלטה הזו של שיעור באוניברסיטה, בעברית, מילה במילה ככל האפשר. '
              'כל 20–40 שניות התחל שורה חדשה עם חותמת זמן בפורמט [HH:MM:SS]. בלי סיכום ובלי הערות — רק התמלול.')


def transcribe(audio: Path, lesson: str) -> tuple[str, float]:
    """→ ('[HH:MM:SS] text' lines, cost).
    Tested on a real Hebrew lecture: gemini-2.5-flash refused (RECITATION) or invented a transcript;
    gemini-3.8-flash with low thinking transcribed it correctly. A refusal → the next model."""
    first = common.settings()['transcribe_model']
    client = _client()
    f = client.files.upload(file=str(audio))
    for _ in range(60):                                     # wait until Google finished processing the upload
        if getattr(getattr(f, 'state', None), 'name', 'ACTIVE') == 'ACTIVE':
            break
        time.sleep(5)
        f = client.files.get(name=f.name)
    text, total = '', 0.0
    try:
        for model in dict.fromkeys([first, 'gemini-3.8-flash', 'gemini-3.5-flash']):
            # ~25k tokens covers a 90-min lecture; the cap keeps a looping model from burning more
            resp = client.models.generate_content(model=model, contents=[f, TRANSCRIBE],
                                                  config=_config(model, 40000, low_thinking=True))
            total += ledger.log(resp, model, 'transcribe', lesson, audio=True)
            text = (resp.text or '').strip()
            if text:
                break
            print(f'  ⚠️ {model} returned no transcript ({getattr((resp.candidates or [None])[0], "finish_reason", "")}) — next model')
    finally:
        try:
            client.files.delete(name=f.name)
        except Exception:
            pass
    return text, total
