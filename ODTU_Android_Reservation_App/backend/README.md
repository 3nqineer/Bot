# ODTÜ reservation backend (single-account starter)

The server checks the official ODTÜ sports reservation website every 300 seconds using Playwright. After **verified** booking, it stops and sends a Firebase Cloud Messaging push message to the paired phone; it never sends SMS or email. The mobile device does not need to remain on.

## Setup on an always-on Windows PC (or a machine with an interactive browser)

1. Install Python 3.11+ and Google Chrome/Playwright Chromium; then in this directory:

   ```sh
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ```

2. Copy `.env.example` to `.env`, generate `APP_API_KEY`:

   ```sh
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. Create your own Firebase project with Cloud Messaging enabled. Download a **Firebase Admin SDK service-account JSON** for the backend and save it as `firebase-service-account.json` in this directory. Never expose or distribute the JSON file. For the phone, configure the same Firebase project with FlutterFire (see `../mobile/README.md`).

4. Sign in manually, on the machine running the backend:

   ```sh
   python login.py
   ```

   A Chromium window opens at `https://rez.metu.edu.tr/`. Type your student credentials **inside the official webpage** and complete CAPTCHA/MFA yourself, then press Enter in the terminal. The credentials are **not collected by this software**; the browser's persistent authenticated session lives in `private_data/browser_profile/` on that computer. Protect that folder like a password.

5. Configure `site_config.json` selectors using the actual **authenticated** booking page: menu navigation, facility selector, date selector, unique row for the requested session, reserve button, final reservation confirmation. The supplied values are **intentionally placeholders**. Booking will not start until they are replaced. For guidance, consult the prior desktop bot's `--inspect` mode (login session pages may include private information; don't share screenshots without redacting).

6. Start the API:

   ```sh
   python -m uvicorn api:app --host 127.0.0.1 --port 8000
   ```

7. Make the API reachable from the phone **only over a secure authenticated connection**. Use a correctly configured HTTPS reverse proxy (or a private VPN plus HTTPS). Never publish the plain HTTP port or the Firebase service account. Backend auth is via `X-API-Key`; mobile app stores it using secure storage.

8. Configure the mobile app with the HTTPS URL and matching API key, enable notifications, choose facility/day/time, press Start.

## Behavior and limitations

- Runs on the server even when the phone is locked or the app is closed, **as long as the server keeps running**.
- Checks immediately and then approximately every 5 minutes after each completed check; pauses on login/CAPTCHA expiration rather than bypassing CAPTCHA. Session expiry must be fixed by manually rerunning `login.py` and restarting monitoring in the app.
- Booking succeeds only on an explicit post-submit confirmation selector (or configured booked-in-slot selector); otherwise it stops at `VERIFY_MANUALLY` to avoid duplicate reservations.
- Stops checking at the scheduled session's starting time, or when the user taps Stop, or upon confirmed booking.
- After five consecutive unexpected errors, stops and displays `ERROR`.
- Push is attempted once after confirmation. If Firebase fails, `CONFIRMED` is still recorded, with a message explaining push failure. Open the app to confirm current state.
- No CAPTCHA-solving, rate-limit bypass, auto-credential collection, or guaranteed reservation.
- This starter is **single-user/single-account**. For multiple students, deploy isolated backends and browser profiles with distinct API keys, or implement real per-user authentication and isolation before releasing to others.
- Check the university's rules for automated use. Keep polling at or above five minutes and stop on errors.

## Verification

From this directory:

```sh
python -m pytest tests -q
```

Tests cover unavailable-to-confirmed state transition, only-one-push policy, manual login and uncertain confirmation handling, safe stop, and five-minute minimum. These are mock-flow tests, not live reservation tests.

## API

All routes except `/health` require `X-API-Key`.

- `GET /status` — one monitor's status and last checked time
- `POST /device` — Firebase device token from phone
- `POST /start` — `{ "facility": "...", "date": "YYYY-MM-DD", "time": "HH:MM" }`
- `POST /stop` — stop after current check completes

## Caution about server shutdowns

Monitor status is persisted in `private_data/state.json`, and `WATCHING` resumes after service restart. To guarantee near-five-minute intervals, configure the backend as a supervised, always-on process, not a sleeping PC.
