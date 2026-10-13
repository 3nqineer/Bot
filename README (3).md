# ODTÜ Spor Rezervasyon Takip — Android edition

**This archive is an Android Flutter source project plus the reservation-checking backend. It is NOT an already-built APK.** A script and GitHub Actions workflow are provided to create `app-release.apk` with a real Flutter/Android build environment. The current editing environment has no Flutter/Android SDK and cannot download it; therefore the APK cannot be generated or installed/tested here.

## What the Android app does

- Choose sports facility, day, and time.
- Start/stop a monitor on your own remote backend.
- See the monitor status and last check time.
- With Firebase configured, receive a native push notification when a booking has been **confirmed** even if the phone app is closed.
- The backend checks about every 300 seconds and stops on confirmed booking, login/CAPTCHA requirement, explicit stop, or fatal/uncertain booking error.
- No SMS or email.

**Do not mistake a successful app build for a working reservation integration.** The private booking pages' selectors are deliberately incomplete because the booking form is not publicly accessible. The backend requires manual login with your own student account, a browser session, and validated booking-page selectors. No CAPTCHA solver is included; use only in accordance with university policy.

## A. Create an APK using GitHub Actions (no Android Studio needed locally)

1. Create a private GitHub repository and upload this folder **including `.github/workflows/android-apk.yml`**. Avoid uploading your `.env`, personal browser session, Firebase Admin service account, or credentials.
2. Open your GitHub repo's **Actions → Build Android APK → Run workflow**. (Pushing source changes also triggers a build.)
3. When the job succeeds, open the run → **Artifacts → ODTU-Spor-Takip-Android-APK**. Download and unzip the artifact; it contains `app-release.apk`.
4. Transfer the APK to Android devices. Android may ask you to approve installations from that file source.

The first build can run **without Firebase**, and will show a prominent in-app warning that push notifications are disabled. To receive native push notifications, follow section C and rebuild with Firebase configuration. Running the unconfigured APK cannot deliver push alerts.

## B. Create an APK on Windows

1. Install [Flutter SDK](https://docs.flutter.dev/get-started/install/windows/mobile), Android Studio with Android SDK, and Python 3. Run `flutter doctor` and complete the recommended setup.
2. Extract this package, open `mobile`, and run `build_android.bat`.
3. The output is `mobile/build/app/outputs/flutter-apk/app-release.apk`.

This local script creates the basic unconfigured APK. For push-enabled builds, follow section C, then run:

```powershell
cd mobile
flutter create --platforms=android --project-name odtu_reservation --org com.communitysport .
# Provide the real lib/firebase_options.dart using flutterfire configure,
# and android/app/google-services.json from the SAME Firebase Android app.
python scripts/prepare_android.py --firebase
flutter pub get
flutter build apk --release --dart-define=ENABLE_PUSH=true
```

## C. Enable notifications (required for the requested behavior)

Push notifications require **your Firebase project**, not a fictitious shared account:

1. Set up Firebase Cloud Messaging and register Android package name **`com.communitysport.odtu_reservation`** with your Firebase project. Obtain the project's Android `google-services.json` and generate `lib/firebase_options.dart` using `flutterfire configure` (set FlutterFire to the same Android package). This replaces the intentional placeholder class in the repo.
2. For **GitHub Actions**, use two repository Actions secrets containing Base64-encoded file bytes: `FIREBASE_OPTIONS_DART_B64` and `FIREBASE_GOOGLE_SERVICES_JSON_B64`. On Windows, you can create each encoded value using PowerShell:

   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes('lib/firebase_options.dart'))
   [Convert]::ToBase64String([IO.File]::ReadAllBytes('android/app/google-services.json'))
   ```

   When **both** secrets are defined, the workflow enables the Google Services plugin and builds with `ENABLE_PUSH=true`. When either is missing, it produces a basic APK without push messaging.
3. Download a **Firebase Admin SDK service-account JSON** for the **backend only**, keep it securely on the server and set `FIREBASE_CREDENTIALS`. Never ship this secret in the APK or git repository.
4. Install the push-enabled build, connect to your backend in settings, and grant notification permission. Confirm that the backend receives your device token.

Firebase project setup is documented at [Firebase Flutter setup](https://firebase.google.com/docs/flutter/setup). Never commit Firebase Admin credentials.

## D. Make actual ODTÜ reservations

1. Set up the always-on Python server following `backend/README.md`. Use Python 3.11+ and `pip install -r requirements.txt` / `python -m playwright install chromium`.
2. Set a random `APP_API_KEY` in backend `.env`; log into the **official** site manually on that backend using `python login.py` and complete CAPTCHA/MFA yourself.
3. Use the authenticated reservation webpage to replace the `REPLACE_...` fields in `backend/site_config.json`. Currently the backend **deliberately refuses to start a reservation** with placeholder selectors. Inspect and verify the UI before making live reservations.
4. Expose only a secure HTTPS API. Put the URL and unique API key into the app's settings. Test `/status` connectivity; then select a slot and start monitoring.
5. Keep the backend computer or server online. Push notifications may arrive with delays and depend on Android notification settings/connectivity. The app's status is the source of truth.

## Important distribution limitation

The *APK can be installed on multiple Android phones*, but the included backend uses a **single account, a single API key, and one monitoring job**. Giving one backend's key to everyone would allow all users to control the same student's booking job, which is insecure. To support multiple people, deploy **isolated servers/credentials** per student or redesign the backend with per-user login, session isolation, permissions, and audit logging before distribution.

Automated reservations may be limited by ODTÜ website terms and anti-bot protections. CAPTCHA must be completed by the person on the official login page; this project does not bypass it.

## Test coverage / limitations

- Python backend tests are included and can run with `python -m pytest backend/tests -q` once dependencies are installed.
- A Flutter smoke test is supplied, but an Android APK was **not compiled or validated in this environment**.
- Exact ODTÜ reservation selectors, Firebase credentials, and a live backend are not present, so a fully functional reservation plus push workflow is not yet validated.
