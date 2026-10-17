"""The parts that broke for a friend before — checked without the university, Gemini or email."""
from datetime import date, datetime

import pytest

from src import common, ledger, moodle, panopto, timetable


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(common, 'STATE', tmp_path / 'state')
    monkeypatch.setattr(common, 'DOCS', tmp_path / 'docs')
    monkeypatch.setattr(common, 'CONFIG', tmp_path / 'config')


def test_term_numbering():
    assert common.term(date(2026, 10, 18)) == '2026-1' and common.term(date(2027, 1, 10)) == '2026-1'
    assert common.term(date(2027, 3, 20)) == '2027-2'


def test_group_folders_from_folder_names():
    sessions = [{'FolderID': 'A', 'FolderName': '(0368200201-2026-1) הסתברות וסטטיסטיקה'},
                {'FolderID': 'B', 'FolderName': '(0368200202-2026-1) הסתברות וסטטיסטיקה'},
                {'FolderID': 'C', 'FolderName': '(0368200201-2025-2) הסתברות — סמסטר קודם'}]
    assert panopto.group_folders(sessions, '03682002', '2026-1') == {'01': 'A', '02': 'B'}


def _sess(day_hhmm_utc: str, name='x'):
    ms = int(datetime.fromisoformat(day_hhmm_utc).replace(tzinfo=__import__('datetime').timezone.utc).timestamp() * 1000)
    return {'StartTime': f'/Date({ms})/', 'SessionName': name, 'DeliveryID': name}


def test_recording_matches_israel_time():
    # 10:00 in Israel on 18/10/2026 (summer time, UTC+3) = 07:00 UTC
    sessions = [_sess('2026-10-18T07:02:00', 'mine'), _sess('2026-10-18T11:00:00', 'later')]
    assert panopto.recording_for(sessions, '2026-10-18', '10:00')['SessionName'] == 'mine'
    assert panopto.recording_for(sessions, '2026-10-19', '10:00') is None


def test_missing_lesson_taken_from_another_group_same_week():
    per = {'01': [], '02': [_sess('2026-10-19T09:00:00', 'g2')], '03': [_sess('2026-10-27T09:00:00', 'next week')]}
    g, s = panopto.same_week_elsewhere(per, '01', '2026-10-18')
    assert g == '02' and s['SessionName'] == 'g2'
    assert panopto.same_week_elsewhere({'01': [], '03': per['03']}, '01', '2026-10-18') is None


def test_gibberish_captions_rejected():
    hebrew = '\n'.join(f'{i}\n00:00:{i:02d},000 --> 00:00:{i + 1:02d},000\nהיום נדבר על משתנים מקריים והתפלגויות שונות {i}'
                       for i in range(40))
    cyrillic = hebrew.replace('היום נדבר על משתנים מקריים והתפלגויות שונות', 'Сегодня мы поговорим о случайных величинах')
    assert panopto.srt_is_good(hebrew) and not panopto.srt_is_good(cyrillic)
    assert panopto.srt_to_transcript(hebrew).startswith('[00:00:00] היום')


def test_empty_recordings_and_noise_transcripts_are_skipped():
    """Real: a 0-minute recording was transcribed into 60k tokens of 'אוקיי' ($0.15) and then summarized."""
    short = {**_sess('2026-10-18T07:00:00', 'empty'), 'Duration': 0}
    real = {**_sess('2026-10-18T07:05:00', 'real'), 'Duration': 5400}
    assert panopto.recording_for([short, real], '2026-10-18', '10:00')['SessionName'] == 'real'
    assert not panopto.text_is_real('אוקיי ' * 5000)
    assert panopto.text_is_real(' '.join(f'מילה{i} משפט ארוך על אינטגרלים' for i in range(200)))


def test_cost_counts_thinking_tokens():
    assert ledger.cost('gemini-3.8-flash', 100_000, 10_000, thinking=20_000) == pytest.approx(0.15 + 0.225)
    assert ledger.cost('some-new-model', 1_000_000, 0) > 0                  # unknown model is never free


def test_hebrew_due_dates():
    assert moodle.parse_he_date('יום ראשון, 17 מאי 2026, 23:59') == '2026-05-17T23:59'
    assert moodle.parse_he_date('17/05/2026, 23:59') == '2026-05-17T23:59'


def test_timetable_propose_and_mine():
    ev = lambda **k: {'course': 'הסתברות', 'number': '03682002', 'date': '2026-10-18', 'time': '10:00', 'end_time': '13:00',
                      'kind': 'שיעור', 'group': '01', 'is_exam': False, 'building': 'דן דוד', 'room': '002', **k}
    events = [ev(), ev(date='2026-10-25'), ev(kind='תרגיל', group='02', date='2026-10-20', time='11:00'),
              ev(kind='בחינה', is_exam=True), ev(number='00000000', course='פתיחת שנה')]
    tt = timetable.propose(events)
    assert tt['confirmed'] is False and len(tt['courses']) == 1 and len(tt['courses'][0]['lessons']) == 2
    assert tt['courses'][0]['lessons'][0]['day'] == 'ראשון'
    assert len(timetable.mine(tt, events)) == 3
    tt['courses'][0]['lessons'] = tt['courses'][0]['lessons'][:1]
    assert timetable.changes(tt, events) == ['הסתברות — תרגיל קב׳ 02']


def test_dashboard_builds(monkeypatch):
    common.save_json('lessons.json', {'k': {'course': 'הסתברות', 'kind': 'שיעור', 'group': '01', 'date': '2026-10-18',
                                            'time': '10:00', 'status': 'other_group', 'from_group': '02', 'cost': 0.12}})
    html = __import__('src.dashboard', fromlist=['x']).build([{'course': 'הסתברות', 'title': 'תרגיל 1', 'homework': True}])
    assert 'dir=\'rtl\'' in html and 'מקבוצה אחרת' in html and 'תרגיל 1' in html
