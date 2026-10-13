# Android mobile client

This is the Flutter Android client for the ODTÜ reservation watcher.

- Use `build_android.bat` from Windows after installing Flutter, Android SDK, and Python.
- Or create a private GitHub repository with the **whole root of this archive** and run `.github/workflows/android-apk.yml` from GitHub Actions to obtain an installable APK as a build artifact.
- Native push notifications require a *real* Firebase project configured using `flutterfire configure` and matching `android/app/google-services.json`, plus rebuilding the APK with `--dart-define=ENABLE_PUSH=true`.
- Without Firebase configuration, the app runs in **connection/status mode only**, not notification mode. A yellow warning in the UI explains this.
- Settings require an HTTPS backend URL and API key; no ODTÜ credentials are stored on the phone.
- The backend, not the Android app, performs the five-minute checks and must remain powered on.

See `../README.md` for full setup, Android build steps, and security caveats.
