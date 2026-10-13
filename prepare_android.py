"""Prepare a freshly generated Flutter Android project. Python 3 stdlib only.

The Flutter template creates Android Gradle files with its own structure;
this intentionally fails explicitly if that structure cannot be recognized.
"""
import argparse
import re
from pathlib import Path

def inject_once(text: str, needle: str, value: str) -> str:
    if value in text:
        return text
    if needle not in text:
        raise RuntimeError(f'Could not locate Android template marker: {needle!r}')
    return text.replace(needle, value + needle, 1)

def configure(root: Path, firebase: bool = False):
    android = root/'android'
    manifest = android/'app/src/main/AndroidManifest.xml'
    if not manifest.exists():
        raise RuntimeError('Android project missing; first run flutter create --platforms android ...')
    xml=manifest.read_text(encoding='utf-8')
    xml=inject_once(xml, '<application', '    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n') if 'android.permission.INTERNET' not in xml else xml
    if 'android.permission.POST_NOTIFICATIONS' not in xml:
        xml=inject_once(xml, '<application', '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n')
    xml=re.sub(r'android:label="[^"]+"', 'android:label="ODTÜ Spor Takip"', xml, count=1)
    manifest.write_text(xml, encoding='utf-8')
    if firebase:
        if not (android/'app/google-services.json').exists():
            raise RuntimeError('Missing android/app/google-services.json')
        options = (root/'lib/firebase_options.dart').read_text(encoding='utf-8')
        if 'BUILD-TIME PLACEHOLDER' in options:
            raise RuntimeError('firebase_options.dart is still the placeholder; run flutterfire configure.')
        settings=android/'settings.gradle.kts'
        app=android/'app/build.gradle.kts'
        if not settings.exists() or not app.exists():
            raise RuntimeError('Expected Flutter Kotlin DSL Android Gradle files')
        settings_text=settings.read_text(encoding='utf-8')
        if 'id("com.google.gms.google-services") version' not in settings_text:
            marker='plugins {'
            if marker not in settings_text:
                raise RuntimeError('Could not find settings.gradle.kts plugins block')
            settings_text=settings_text.replace(marker, marker+'\n    id("com.google.gms.google-services") version "4.4.4" apply false',1)
            settings.write_text(settings_text,encoding='utf-8')
        app_text=app.read_text(encoding='utf-8')
        if 'id("com.google.gms.google-services")' not in app_text:
            marker='plugins {'
            if marker not in app_text:
                raise RuntimeError('Could not find app/build.gradle.kts plugins block')
            app_text=app_text.replace(marker, marker+'\n    id("com.google.gms.google-services")',1)
            app.write_text(app_text,encoding='utf-8')
    return manifest

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--firebase', action='store_true')
    args=parser.parse_args()
    print('Prepared', configure(Path(__file__).resolve().parents[1], args.firebase))
