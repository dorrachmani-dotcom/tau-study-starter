"""Shared paths, settings and time helpers. Every time-of-day decision is Israel time (GitHub runs in UTC)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'config'
STATE = ROOT / 'state'
SUMMARIES = ROOT / 'summaries'
DOCS = ROOT / 'docs'
TZ = ZoneInfo('Asia/Jerusalem')

try:                                     # local runs: secrets from .env (GitHub Actions: repository secrets)
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except ImportError:
    pass


def now() -> datetime:
    """Israel wall-clock time, naive."""
    return datetime.now(timezone.utc).astimezone(TZ).replace(tzinfo=None)


def to_israel(dt_utc: datetime) -> datetime:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(TZ).replace(tzinfo=None)


def settings() -> dict:
    p = CONFIG / 'settings.yaml'
    d = yaml.safe_load(p.read_text(encoding='utf-8')) if p.exists() else {}
    d = d or {}
    d.setdefault('monthly_cap_usd', 8.0)
    d.setdefault('lookback_days', 3)
    d.setdefault('missing_after_hours', 20)
    d.setdefault('summary_model', 'gemini-3.8-flash')
    d.setdefault('transcribe_model', 'gemini-3.8-flash')
    d.setdefault('email_to', os.getenv('EMAIL_TO') or os.getenv('GMAIL_ADDRESS', ''))
    return d


def load_json(name: str, default):
    p = STATE / name
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save_json(name: str, obj) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')


def term(today=None) -> str:
    """TAU numbering in Panopto folder names: semester A (Oct–Feb) = '<year it starts>-1', semester B = '<year>-2'."""
    t = today or now().date()
    if t.month >= 9:
        return f'{t.year}-1'
    if t.month <= 2:
        return f'{t.year - 1}-1'
    return f'{t.year}-2'
