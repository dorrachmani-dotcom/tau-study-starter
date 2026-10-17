"""Every paid AI call, with its real cost — including "thinking" tokens (leaving them out made a friend's ledger
3–5x lower than the actual Google invoice). A hard monthly cap stops all paid work.

state/ledger.json: [{ts, op, model, in, out, thinking, cost, lesson}]
"""
from __future__ import annotations

from . import common

# USD per 1M tokens. Erring high on purpose — this feeds the cap. Update from Google's pricing page.
PRICING = {
    'gemini-3.8-flash': {'in': 1.50, 'out': 7.50},
    'gemini-3.5-flash': {'in': 1.50, 'out': 9.00},
    'gemini-2.5-flash': {'in': 0.30, 'out': 2.50, 'audio_in': 1.00},
    'gemini-2.5-flash-lite': {'in': 0.10, 'out': 0.40, 'audio_in': 0.30},
    'gemini-2.5-pro': {'in': 1.25, 'out': 10.00},
}
FALLBACK = {'in': 2.00, 'out': 12.00, 'audio_in': 2.00}      # an unknown model is never "free"


def cost(model: str, tokens_in: int, tokens_out: int, thinking: int = 0, audio: bool = False) -> float:
    p = PRICING.get(model, FALLBACK)
    rate_in = p.get('audio_in', p['in']) if audio else p['in']
    return round(tokens_in / 1e6 * rate_in + (tokens_out + thinking) / 1e6 * p['out'], 6)


def log(resp, model: str, op: str, lesson: str = '', audio: bool = False) -> float:
    """Record one Gemini response (usage_metadata) → its cost."""
    um = getattr(resp, 'usage_metadata', None)
    t_in = int(getattr(um, 'prompt_token_count', 0) or 0)
    t_out = int(getattr(um, 'candidates_token_count', 0) or 0)
    t_think = int(getattr(um, 'thoughts_token_count', 0) or 0)
    c = cost(model, t_in, t_out, t_think, audio)
    rows = common.load_json('ledger.json', [])
    rows.append({'ts': common.now().isoformat(timespec='seconds'), 'op': op, 'model': model, 'in': t_in,
                 'out': t_out, 'thinking': t_think, 'cost': c, 'lesson': lesson})
    common.save_json('ledger.json', rows)
    return c


def month_total(month: str | None = None, rows: list | None = None) -> float:
    month = month or common.now().strftime('%Y-%m')
    rows = rows if rows is not None else common.load_json('ledger.json', [])
    return round(sum(r['cost'] for r in rows if r['ts'].startswith(month)), 4)


def lesson_total(lesson: str, rows: list | None = None) -> float:
    rows = rows if rows is not None else common.load_json('ledger.json', [])
    return round(sum(r['cost'] for r in rows if r.get('lesson') == lesson), 4)


def over_cap() -> bool:
    return month_total() >= float(common.settings()['monthly_cap_usd'])
