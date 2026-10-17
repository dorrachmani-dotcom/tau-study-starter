"""Step 1, before anything else: can this machine (GitHub's servers, or my computer) log in to the university?
Checks Panopto, Moodle and my.tau — nothing paid, nothing emailed, no secret printed."""
from __future__ import annotations

import sys

from . import common, panopto, timetable
from .tau_login import moodle_session, panopto_session


def main() -> int:
    ok = True
    try:
        events = timetable.fetch()
        les = timetable.lessons(events)
        print(f'✅ my.tau: {len(events)} אירועים, {len(les)} שיעורים/תרגולים')
    except Exception as e:
        ok, les = False, []
        print(f'❌ my.tau: {e}')
    try:
        s = panopto_session()
        print('✅ Panopto: התחברות הצליחה')
        seen = set()
        for e in les:
            if e['number'] in seen:
                continue
            seen.add(e['number'])
            f = panopto.find_folders(s, e['course'], e['number'])
            print(f"   {'✅' if f else '⏳'} {e['course']}: קבוצות בפנופטו {sorted(f) or '(עוד אין הקלטות)'}")
    except Exception as e:
        ok = False
        print(f'❌ Panopto: {e}')
    try:
        moodle_session()
        print('✅ Moodle: התחברות הצליחה')
    except Exception as e:
        ok = False
        print(f'❌ Moodle: {e}')
    print('\nהכל עובד — אפשר להמשיך.' if ok else '\nמשהו לא עובד. אם זה רץ ב-GitHub — לנסות במחשב (README, "הרצה במחשב").')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
