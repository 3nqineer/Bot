"""Firebase Cloud Messaging: no SMS or email. Credentials stay on the server."""
import asyncio
import os
from pathlib import Path


def send_push_sync(device_token: str, job: dict):
    import firebase_admin
    from firebase_admin import credentials, messaging
    credential_path = os.getenv('FIREBASE_CREDENTIALS', 'firebase-service-account.json')
    if not Path(credential_path).is_file():
        raise RuntimeError('FIREBASE_CREDENTIALS not configured on backend')
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(credentials.Certificate(credential_path))
    payload = messaging.Message(
        notification=messaging.Notification(
            title='ODTÜ Rezervasyon Onaylandı',
            body=f"{job['facility']} · {job['date']} · {job['time']}"
        ),
        data={'type': 'reservation_confirmed'},
        token=device_token,
    )
    return messaging.send(payload)


async def send_push(device_token: str, job: dict):
    return await asyncio.to_thread(send_push_sync, device_token, job)
