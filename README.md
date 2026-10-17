# 📚 tau-study-starter

מערכת אישית לסטודנטים באוניברסיטת תל אביב. היא רצה ב-GitHub Actions: בלי שרת, ובלי שהמחשב צריך להיות דלוק.

**מה היא עושה כל ערב:**
- 🗓️ **בודקת את מערכת השעות שלך** ב-my.tau: קורסים, קבוצות, שעות וחדרים.
- 📄 **מסכמת שיעורים:** כל שיעור או תרגול של הקבוצה שלך נשלח אליך במייל כסיכום PDF בעברית, כולל כמה עלה.
- 🔁 **משלימה שיעור שבוטל או לא הוקלט:** מוצאת את אותו שיעור מקבוצה אחרת של הקורס, ומציינת את זה.
- 📂 **אוספת חומרים ממודל:** כל קובץ חדש נשמר ונשלח. מטלות נשמרות עם תאריך הגשה, ותזכורת נשלחת 48 שעות לפני.
- 💰 **עוקבת אחרי עלויות:**
  - העלות של כל פעולה.
  - דוח חודשי ב-1 לחודש.
  - תקרה חודשית. מעליה הכול נעצר ומקבלים הודעה.
- 📊 **דשבורד** בכל מייל, ובקובץ `docs/dashboard.html`.
- 📚 **(רשות) NotebookLM:** כל הסיכומים, המטלות והחומרים ממודל נכנסים למחברת לכל קורס, וממנה אפשר לשאול שאלות בחינם.

העלות היא רק Gemini:
- **הרצאה עם כתוביות בפנופטו (רוב ההרצאות):** בערך $0.08.
- **הרצאה בלי כתוביות (תמלול):** בערך $0.40.

סמסטר רגיל יוצא בערך $3–8 בחודש.

> הקוד נבנה ונבדק על מערכת שרצה כבר סמסטר שלם. הוא בדק ונמנע מבעיות שקרו בפועל:
> - כתוביות "עבריות" שהן בעצם ג'יבריש בקירילית.
> - הקלטה ריקה שתומללה ל-60 אלף טוקנים של "אוקיי".
> - חשבונית אמיתית שיצאה פי 3–5 ממה שנרשם, כי טוקני ה-thinking לא נספרו.

---

## הקמה (בערך שעה)

הדרך הקלה: לפתוח את Claude Code בתיקיית הפרויקט ולהדביק את התוכן של [`SETUP_PROMPT.md`](SETUP_PROMPT.md). הוא יעבור איתך על הכול. אם רוצים לבד:

1. **Use this template** → ליצור repo **פרטי** משלך. חשוב: הסיכומים והחומרים נשמרים בו.
2. **מפתחות:**
   - Gemini: https://aistudio.google.com/apikey, עם חיוב פעיל ותקרה ב-Google Cloud.
   - Gmail: סיסמת אפליקציה (App Password). חשבון Google ← אבטחה ← אימות דו-שלבי ← סיסמאות לאפליקציות.
3. **Settings → Secrets and variables → Actions → New repository secret:**
   `TAU_USERNAME`, `TAU_ID` (ת״ז), `TAU_PASSWORD`, `GEMINI_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`
4. **Actions → setup → Run workflow → `feasibility`:** בודק ש-GitHub מצליח להתחבר לאוניברסיטה. אם לא, ראה "הרצה במחשב" למטה.
5. **Actions → setup → `timetable`:** יוצר את `config/timetable.yaml` מתוך my.tau.
   - לבדוק את הקובץ ולתקן אם צריך. `summarize: false` = לא לסכם את הקורס הזה.
   - לשנות `confirmed: true`. **עד שלא מאשרים, שום דבר לא רץ.**
6. **(רשות) `config/settings.yaml`:** תקרה חודשית, כתובת מייל.
7. **בדיקה ראשונה בזול:** Actions → nightly → Run workflow, עם `--only "שם קורס" --clip-min 5`.

מעכשיו זה רץ לבד כל ערב בין ראשון לשישי.

## NotebookLM (רשות)

NotebookLM לא מציע API רשמי, אז ההתחברות היא התחברות Google רגילה.

1. **במחשב, פעם אחת:**

   ```
   pip install -r requirements.txt -r requirements-notebooklm.txt
   python -m playwright install chromium
   notebooklm login
   ```

2. **מהמחשב:** `python -m src.notebooklm` מעלה את כל מה שחדש (סיכומים, חומרים, מטלות) למחברת לכל קורס. עושים קודם `git pull`.
3. **אוטומטי מ-GitHub:** מעתיקים את התוכן של `~/.notebooklm/profiles/default/storage_state.json` לסוד `NOTEBOOKLM_STORAGE`.
   - שימו לב: Google עלול לנתק התחברות שמשמשת משרתים משתנים.
   - אם זה קורה, תקבל מייל, ואפשר להמשיך מהמחשב.

## הרצה במחשב (אם GitHub נחסם)

```
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env      # ולמלא
python -m src.feasibility
python -m src.timetable --propose
python -m src.nightly
```

ב-Windows אפשר לתזמן את `python -m src.nightly` ב-Task Scheduler כל ערב, עם "Run task as soon as possible after a scheduled start is missed".

## מבנה

| קובץ | מה |
|---|---|
| `src/tau_login.py` | התחברות SSO לאוניברסיטה (Panopto, מודל, my.tau) |
| `src/timetable.py` | מערכת השעות מ-my.tau, הצעה, אישור ושינויים |
| `src/panopto.py` | תיקיות לפי קבוצה, מציאת ההקלטה, כתוביות ובדיקת ג'יבריש, אודיו |
| `src/ai.py` | סיכום ותמלול עם Gemini (הפרומפט ב-`prompts/summary.md`) |
| `src/moodle.py` | קבצים ומטלות |
| `src/ledger.py` | עלויות, כולל thinking, ותקרה |
| `src/dashboard.py` / `src/mailer.py` | דשבורד ומייל |
| `src/nightly.py` | הריצה הלילית |
| `src/monthly.py` | דוח חודשי |
| `src/notebooklm.py` | העלאה ל-NotebookLM |

בדיקות: `pytest`.

## אבטחה
- **סיסמאות:** רק ב-GitHub Secrets או בקובץ `.env` אצלך. הן לא מודפסות ולא נשמרות בקוד.
- **ה-repo חייב להיות פרטי:** יש בו את הסיכומים והחומרים שלך.
- **התקרה החודשית** עוצרת הכול לפני שזה נהיה יקר.
