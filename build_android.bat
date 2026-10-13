@echo off
setlocal
cd /d "%~dp0"
where flutter >nul 2>nul
if errorlevel 1 (
  echo Flutter SDK not found. Install Flutter and Android Studio, then retry.
  pause
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 not found. Required for Android project configuration.
  pause
  exit /b 1
)
call flutter create --platforms=android --project-name odtu_reservation --org com.communitysport .
if errorlevel 1 goto :fail
call python scripts\prepare_android.py
if errorlevel 1 goto :fail
call flutter pub get
if errorlevel 1 goto :fail
call flutter build apk --release
if errorlevel 1 goto :fail
echo.
echo APK created at:
echo %CD%\build\app\outputs\flutter-apk\app-release.apk
echo Push notifications need Firebase setup and a Firebase-enabled rebuild.
pause
exit /b 0
:fail
echo Build failed. See the error above.
pause
exit /b 1
