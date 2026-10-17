"""TAU single sign-on (NIDP) with Playwright — the same login opens Panopto, Moodle and my.tau.

Secrets come from the environment only (GitHub secrets / .env): TAU_USERNAME, TAU_ID, TAU_PASSWORD.
They are typed into the university's own form and never printed or written anywhere.
"""
from __future__ import annotations

import os

import requests

PANOPTO = 'https://tau.cloud.panopto.eu'


def fill_nidp(page) -> None:
    """On the university's login page: user, ID number, password, submit."""
    if 'tau.ac.il' not in page.url:
        return
    page.locator('#Ecom_User_ID').fill(os.getenv('TAU_USERNAME', ''))
    if os.getenv('TAU_ID'):
        try:
            page.locator('#Ecom_User_Pid').fill(os.getenv('TAU_ID', ''))
        except Exception:
            pass
    page.locator('#Ecom_Password').fill(os.getenv('TAU_PASSWORD', ''))
    page.locator('#loginButton').click()
    page.wait_for_timeout(8000)
    page.wait_for_load_state('networkidle')


MOODLE = 'https://moodle.tau.ac.il'


def moodle_session() -> requests.Session:
    """Log in to Moodle through the university SSO → a requests session with the cookies."""
    if not os.getenv('TAU_USERNAME') or not os.getenv('TAU_PASSWORD'):
        raise RuntimeError('TAU_USERNAME / TAU_PASSWORD are not set')
    from playwright.sync_api import sync_playwright
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0'})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f'{MOODLE}/login/index.php')
        page.wait_for_load_state('networkidle')
        for sel in ('a[href*="shibboleth"]', 'a[href*="saml"]', 'a[href*="nidp"]', 'text=SSO'):
            try:
                page.click(sel, timeout=2500)
                break
            except Exception:
                continue
        page.wait_for_load_state('networkidle')
        fill_nidp(page)
        if 'moodle.tau.ac.il' not in page.url:
            browser.close()
            raise RuntimeError('Moodle login failed')
        for c in ctx.cookies():
            s.cookies.set(c['name'], c['value'], domain=c.get('domain', '').lstrip('.'))
        browser.close()
    return s


def panopto_session() -> requests.Session:
    """Log in to Panopto through the university SSO → a requests session with the cookies."""
    if not os.getenv('TAU_USERNAME') or not os.getenv('TAU_PASSWORD'):
        raise RuntimeError('TAU_USERNAME / TAU_PASSWORD are not set')
    from playwright.sync_api import sync_playwright
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0'})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f'{PANOPTO}/Panopto/Pages/Auth/Login.aspx')
        page.wait_for_load_state('networkidle')
        page.click('#PageContentPlaceholder_loginControl_externalLoginButton')
        page.wait_for_load_state('networkidle')
        fill_nidp(page)
        page.goto(f'{PANOPTO}/Panopto/Pages/Home.aspx')
        page.wait_for_load_state('networkidle')
        if 'login' in page.url.lower() or 'Sign In' in page.title():
            browser.close()
            raise RuntimeError('Panopto login failed (check the TAU_* secrets; the university may also block this network)')
        for c in ctx.cookies():
            s.cookies.set(c['name'], c['value'], domain=c.get('domain', '').lstrip('.'))
        browser.close()
    return s
