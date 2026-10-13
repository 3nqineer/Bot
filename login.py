"""One-time manual login on the backend host. Never asks for or logs your password.

All CAPTCHA and any MFA are completed interactively inside the official site.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'private_data'

async def main():
    DATA.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(DATA / 'browser_profile'), headless=False, locale='tr-TR',
            timezone_id='Europe/Istanbul')
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto('https://rez.metu.edu.tr/', wait_until='domcontentloaded')
            print('Sign in on the official website in the open browser. Solve CAPTCHA yourself.')
            print('After you are logged in, press Enter in THIS terminal to save the browser session.')
            await asyncio.to_thread(input)
            if await page.locator('input[type="password"]:visible').count():
                raise RuntimeError('A password box is still visible. Login may have failed.')
            print('Browser session saved. Close this terminal after the browser window disappears.')
        finally:
            await context.close()

if __name__ == '__main__':
    asyncio.run(main())
