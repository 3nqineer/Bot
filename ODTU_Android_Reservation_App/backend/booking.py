"""Site-specific reservation adapter. Does NOT attempt to solve or bypass CAPTCHA.

Configuration uses selectors from the authenticated ODTU sports reservation page.
The provided placeholders MUST be replaced before booking is enabled.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

SITE_ORIGIN = 'https://rez.metu.edu.tr'

class BookingError(Exception):
    pass

class LoginRequired(BookingError):
    pass

class BookingUncertain(BookingError):
    """Submission may have gone through: NEVER automatically retry."""
    pass

class SetupRequired(BookingError):
    pass


def load_site_config(path: Path):
    config = json.loads(path.read_text(encoding='utf-8'))
    for field in ('site_url', 'steps', 'slot_selector', 'book_button_selector', 'success_selector'):
        if field not in config:
            raise SetupRequired(f'Missing {field} in site_config.json')
    for url in (config['site_url'], config.get('booking_url', '')):
        if url and (urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'rez.metu.edu.tr'):
            raise SetupRequired('Only https://rez.metu.edu.tr/ is permitted as a booking URL')
    for name in ('slot_selector', 'book_button_selector', 'success_selector'):
        if not config[name] or 'REPLACE_' in config[name]:
            raise SetupRequired('Configure the real post-login selectors in site_config.json')
    for step in config['steps']:
        if any('REPLACE_' in str(v) for v in step.values()):
            raise SetupRequired('Configure the real navigation steps in site_config.json')
    return config


def fmt(string: str, job: dict):
    for k in ('facility', 'date', 'time'):
        string = str(string).replace('{' + k + '}', str(job[k]))
    return string


async def exists(root, selector: str):
    return bool(selector and await root.locator(selector).count() and await root.locator(selector).first.is_visible())


async def login_required(page):
    return (await page.locator('input[type="password"]:visible').count()) > 0


async def captcha_required(page):
    selectors = ('iframe[src*="recaptcha" i]', 'iframe[src*="hcaptcha" i]',
                 '[id*="captcha" i]', '[name*="captcha" i]', 'img[src*="captcha" i]')
    for selector in selectors:
        if await page.locator(selector).count() and await page.locator(selector).first.is_visible():
            return True
    return False


async def apply_steps(page, config: dict, job: dict):
    for step in config['steps']:
        action = step['action']
        selector = fmt(step.get('selector', ''), job)
        value = fmt(step.get('value', ''), job)
        node = page.locator(selector) if selector else None
        if action == 'click':
            await node.click(timeout=10000)
        elif action == 'fill':
            await node.fill(value, timeout=10000)
        elif action == 'select_label':
            await node.select_option(label=value, timeout=10000)
        elif action == 'select_value':
            await node.select_option(value=value, timeout=10000)
        elif action == 'wait_visible':
            await node.wait_for(state='visible', timeout=15000)
        elif action == 'click_text':
            await page.get_by_text(value, exact=True).click(timeout=10000)
        else:
            raise SetupRequired(f'Unsupported step: {action}')
        await page.wait_for_timeout(300)


async def check_and_book(job: dict, profile_dir: Path, site_config_file: Path):
    """Returns 'UNAVAILABLE' or 'CONFIRMED'. User must log in via login.py first."""
    cfg = load_site_config(site_config_file)
    if not profile_dir.exists():
        raise LoginRequired('No saved ODTU login session. Run login.py on the host machine.')
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(profile_dir), headless=True, locale='tr-TR', timezone_id='Europe/Istanbul',
            args=['--disable-dev-shm-usage'],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            entry = cfg.get('booking_url') or cfg['site_url']
            await page.goto(entry, wait_until='domcontentloaded', timeout=30000)
            if await login_required(page) or await captcha_required(page):
                raise LoginRequired('Login expired or CAPTCHA appeared. Re-login manually on the host.')
            await apply_steps(page, cfg, job)
            if await login_required(page) or await captcha_required(page):
                raise LoginRequired('Manual login or CAPTCHA required')
            rows = page.locator(fmt(cfg['slot_selector'], job))
            count = await rows.count()
            if count == 0:
                unavailable = fmt(cfg.get('unavailable_selector', ''), job)
                if unavailable and await exists(page, unavailable):
                    return 'UNAVAILABLE'
                raise BookingError('Target slot not found; selectors/page may have changed')
            if count != 1:
                raise BookingError(f'Target selector matched {count} rows; booking refused')
            row = rows.first
            booked = fmt(cfg.get('already_booked_selector', ''), job)
            if await exists(row, booked):
                return 'CONFIRMED'
            reserve_button = row.locator(fmt(cfg['book_button_selector'], job))
            if (not await reserve_button.count() or not await reserve_button.first.is_visible()
                    or not await reserve_button.first.is_enabled()):
                return 'UNAVAILABLE'
            # After clicking, any unexpected failure is UNCERTAIN, not safe to retry.
            try:
                await reserve_button.first.click(timeout=10000)
                confirm = fmt(cfg.get('confirm_button_selector', ''), job)
                if confirm:
                    await page.locator(confirm).first.click(timeout=10000)
                await page.locator(fmt(cfg['success_selector'], job)).first.wait_for(
                    state='visible', timeout=15000)
                return 'CONFIRMED'
            except Exception as e:
                raise BookingUncertain('Clicked reserve but could not verify success. Check manually.') from e
        finally:
            await context.close()
