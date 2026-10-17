"""
PDF Generator - ממיר Markdown ל-PDF עם WeasyPrint (RTL מלא)
"""

import sys
import re
import os
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass


def preprocess_markdown(md_text: str) -> str:
    """ממיר טבלאות markdown לרשימות, מסיר מספור כותרות"""
    lines = md_text.split('\n')
    result = []
    for line in lines:
        # טבלת separator — דלג
        if re.match(r'^\s*\|[\s\-\|:]+\|\s*$', line):
            continue
        # שורת טבלה — המר לרשימה
        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            cells = [c for c in cells if c]
            if cells:
                result.append('- ' + ' — '.join(cells))
            continue
        # הסר מספור מכותרות: "## 1. נושא" → "## נושא"
        line = re.sub(r'^(#{1,4})\s+\d+\.\s+', r'\1 ', line)
        result.append(line)
    return '\n'.join(result)


def _escape_math(content: str) -> str:
    """HTML-escape math content so it survives HTML parsing but KaTeX can read textContent"""
    return content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def inline_to_html(text: str) -> str:
    """המרת inline markdown לHTML"""
    # Protect $...$ math from other substitutions: extract first, replace at end
    math_placeholders = {}
    counter = [0]

    def save_math(m):
        key = f'\x00MATH{counter[0]}\x00'
        math_placeholders[key] = f'<span class="math">{_escape_math(m.group(1))}</span>'
        counter[0] += 1
        return key

    # Extract inline math before any other processing
    text = re.sub(r'\$([^$\n]+?)\$', save_math, text)

    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Inline code (only for actual code, not math)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Linked timestamps [HH:MM:SS](panopto-url) → clickable (utils/panopto_links)
    text = re.sub(r'\[(\d{2}:\d{2}:\d{2})\]\((https?://[^)\s]+)\)',
                  r'<a class="ts" href="\2">[\1]</a>', text)
    # Other markdown links [label](url)
    text = re.sub(r'\[([^\]\n]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', text)
    # Plain timestamps [HH:MM:SS] (not followed by a link target)
    text = re.sub(r'\[(\d{2}:\d{2}:\d{2})\](?!\()',
                  r'<span class="ts">[\1]</span>', text)

    # Restore math spans
    for key, val in math_placeholders.items():
        text = text.replace(key, val)

    return text


def markdown_to_html_full(md_text: str, title: str = "", course_name: str = "") -> str:
    """ממיר Markdown ל-HTML מלא עם CSS RTL לPDF"""
    md_text = preprocess_markdown(md_text)

    css = """
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;700&display=swap');

    * { box-sizing: border-box; }

    body {
        direction: rtl;
        font-family: 'Heebo', Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.8;
        color: #1a1a1a;
        margin: 0;
        padding: 20mm 18mm 20mm 18mm;
    }

    .header {
        border-bottom: 3px solid #3498db;
        margin-bottom: 16pt;
        padding-bottom: 8pt;
    }

    .course-name {
        font-size: 9pt;
        color: #666;
        margin: 0;
    }

    .lecture-title {
        font-size: 20pt;
        font-weight: 700;
        color: #1a3c6e;
        margin: 4pt 0 0 0;
    }

    h1 {
        font-size: 16pt;
        font-weight: 700;
        color: #1a3c6e;
        border-bottom: 2px solid #3498db;
        padding-bottom: 4pt;
        margin-top: 18pt;
        margin-bottom: 8pt;
    }

    h2 {
        font-size: 13pt;
        font-weight: 700;
        color: #2c5282;
        border-right: 4px solid #3498db;
        padding-right: 8pt;
        margin-top: 14pt;
        margin-bottom: 6pt;
    }

    h3 {
        font-size: 11pt;
        font-weight: 700;
        color: #4a5568;
        margin-top: 10pt;
        margin-bottom: 4pt;
    }

    h4 {
        font-size: 10pt;
        font-weight: 700;
        color: #666;
        margin-top: 8pt;
        margin-bottom: 4pt;
    }

    p {
        margin: 5pt 0;
        text-align: right;
    }

    ul, ol {
        padding-right: 20pt;
        padding-left: 0;
        margin: 6pt 0;
    }

    li {
        margin: 3pt 0;
        text-align: right;
    }

    strong {
        color: #c0392b;
        font-weight: 700;
    }

    code {
        background: #f0f4f8;
        padding: 1pt 4pt;
        border-radius: 3pt;
        font-family: 'Courier New', monospace;
        font-size: 9pt;
        direction: ltr;
        display: inline-block;
    }

    pre {
        background: #f0f4f8;
        padding: 10pt;
        border-radius: 5pt;
        border-right: 3px solid #3498db;
        direction: ltr;
        text-align: left;
        font-family: 'Courier New', monospace;
        font-size: 9pt;
        white-space: pre-wrap;
        margin: 8pt 0;
    }

    pre code {
        background: none;
        padding: 0;
        direction: ltr;
    }

    .math {
        direction: ltr;
        display: inline-block;
    }

    .math-block {
        direction: ltr;
        display: block;
        text-align: center;
        margin: 8pt 0;
        overflow-x: auto;
    }

    .katex { font-size: 1em; }

    .ts {
        color: #718096;
        font-size: 8pt;
        font-family: monospace;
        direction: ltr;
        display: inline-block;
    }

    blockquote {
        border-right: 4px solid #3498db;
        padding: 6pt 10pt;
        margin: 6pt 0;
        background: #f8faff;
        color: #555;
        border-radius: 0 4pt 4pt 0;
    }

    hr {
        border: none;
        border-top: 1px solid #e2e8f0;
        margin: 12pt 0;
    }
    """

    # בנה header
    header_html = f'''
    <div class="header">
        <p class="course-name">{course_name}</p>
        <p class="lecture-title">{title}</p>
    </div>
    ''' if (title or course_name) else ''

    # המר markdown לHTML
    lines = md_text.split('\n')
    body_parts = []
    in_code = False
    in_list = False
    in_ol = False
    code_lines = []

    def close_list():
        nonlocal in_list, in_ol
        if in_list:
            body_parts.append('</ul>')
            in_list = False
        elif in_ol:
            body_parts.append('</ol>')
            in_ol = False

    in_display_math = False
    display_math_lines = []

    for line in lines:
        # Display math block $$...$$ (opening/closing on its own line)
        if line.strip() == '$$':
            close_list()
            if in_display_math:
                content = _escape_math('\n'.join(display_math_lines))
                body_parts.append(f'<div class="math-block">{content}</div>')
                display_math_lines = []
                in_display_math = False
            else:
                in_display_math = True
            continue

        if in_display_math:
            display_math_lines.append(line)
            continue

        # Inline display math $$...$$ on one line
        if line.strip().startswith('$$') and line.strip().endswith('$$') and len(line.strip()) > 4:
            close_list()
            content = _escape_math(line.strip()[2:-2])
            body_parts.append(f'<div class="math-block">{content}</div>')
            continue

        # Code fence
        if line.startswith('```'):
            close_list()
            if in_code:
                body_parts.append('<pre><code>' + '\n'.join(code_lines) + '</code></pre>')
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
            continue

        # HR
        if line.strip() in ('---', '***', '___'):
            close_list()
            body_parts.append('<hr>')
            continue

        # Headers
        if line.startswith('#### '):
            close_list()
            body_parts.append(f'<h4>{inline_to_html(line[5:])}</h4>')
        elif line.startswith('### '):
            close_list()
            body_parts.append(f'<h3>{inline_to_html(line[4:])}</h3>')
        elif line.startswith('## '):
            close_list()
            body_parts.append(f'<h2>{inline_to_html(line[3:])}</h2>')
        elif line.startswith('# '):
            close_list()
            body_parts.append(f'<h1>{inline_to_html(line[2:])}</h1>')

        # Blockquote
        elif line.startswith('> '):
            close_list()
            body_parts.append(f'<blockquote>{inline_to_html(line[2:])}</blockquote>')

        # Ordered list
        elif re.match(r'^\d+[\.)]\s', line):
            if not in_ol:
                close_list()
                body_parts.append('<ol>')
                in_ol = True
            content = re.sub(r'^\d+[\.)]\s+', '', line)
            body_parts.append(f'<li>{inline_to_html(content)}</li>')

        # Unordered list
        elif line.startswith('- ') or line.startswith('* '):
            if not in_list:
                close_list()
                body_parts.append('<ul>')
                in_list = True
            body_parts.append(f'<li>{inline_to_html(line[2:])}</li>')

        # Empty line
        elif not line.strip():
            close_list()
            body_parts.append('<p>&nbsp;</p>')

        # Paragraph
        else:
            close_list()
            body_parts.append(f'<p>{inline_to_html(line)}</p>')

    close_list()

    body_html = '\n'.join(body_parts)

    katex_js = """
<script>
document.addEventListener("DOMContentLoaded", function() {
    // Render inline math spans
    document.querySelectorAll('.math').forEach(function(el) {
        try {
            katex.render(el.textContent, el, {throwOnError: false, displayMode: false});
        } catch(e) {}
    });
    // Render display math spans
    document.querySelectorAll('.math-block').forEach(function(el) {
        try {
            katex.render(el.textContent, el, {throwOnError: false, displayMode: true});
        } catch(e) {}
    });
});
</script>
"""

    return f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<style>
{css}
</style>
</head>
<body>
{header_html}
{body_html}
{katex_js}
</body>
</html>'''


def markdown_to_pdf(md_text: str, output_path: str, title: str = "", course_name: str = "") -> str:
    """ממיר Markdown ל-PDF באמצעות Playwright (Chromium) — RTL מלא"""
    import tempfile
    from playwright.sync_api import sync_playwright

    html_content = markdown_to_html_full(md_text, title=title, course_name=course_name)

    # Write HTML to a temp file (Playwright needs a file:// URL for local fonts)
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', suffix='.html', delete=False
    ) as f:
        f.write(html_content)
        tmp_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file:///{tmp_path.replace(chr(92), '/')}")
            # Wait for KaTeX CDN + fonts to load and math to render
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(1500)  # Give KaTeX JS time to render math
            page.pdf(
                path=output_path,
                format='A4',
                margin={'top': '20mm', 'bottom': '20mm',
                        'left': '18mm', 'right': '18mm'},
                print_background=True
            )
            browser.close()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return output_path


if __name__ == "__main__":
    sample = """# סיכום הרצאה 1

## אינטגרלים לא מסוימים

**הגדרה**: פונקציה $F(x)$ נקראת פונקציה קדומה של $f(x)$ אם $F'(x) = f(x)$.

### נוסחה בסיסית

- הכלל: $\\int x^n dx = \\frac{x^{n+1}}{n+1} + C$ כאשר $n \\neq -1$
- קבוע האינטגרציה C חשוב תמיד

## דוגמה פתורה

חשב את $\\int 3x^2 dx$:

1. לפי הכלל: $n=2$
2. התוצאה: $x^3 + C$

**שימו לב**: אל תשכח את הקבוע!
"""
    path = markdown_to_pdf(sample, "data/test_playwright.pdf", "הרצאה 1", "חדו\"א 2ב")
    print(f"PDF: {path}, size: {os.path.getsize(path)} bytes")
