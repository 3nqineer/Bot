"""Single-account background polling worker with persistent state and safe stop behavior."""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Istanbul')


def local_now():
    return datetime.now(TZ)


def iso():
    return local_now().isoformat(timespec='seconds')


class ReservationWorker:
    def __init__(self, state_file: Path, checker, notifier, poll_seconds: int = 300):
        if poll_seconds < 300:
            raise ValueError('Polling must be at least five minutes')
        self.state_file = state_file
        self.checker = checker
        self.notifier = notifier
        self.poll_seconds = poll_seconds
        self.lock = asyncio.Lock()
        self.wakeup = asyncio.Event()
        self.job = None
        self.status = 'IDLE'
        self.last_checked = None
        self.last_message = 'No reservation monitoring started'
        self.error_count = 0
        self.confirmed_at = None
        self.push_sent = False
        self.device_token = None
        self._task = None
        self._load()

    def _load(self):
        if not self.state_file.exists():
            return
        data = json.loads(self.state_file.read_text(encoding='utf-8'))
        self.job = data.get('job')
        self.status = data.get('status', 'IDLE')
        self.last_checked = data.get('last_checked')
        self.last_message = data.get('last_message', '')
        self.error_count = data.get('error_count', 0)
        self.confirmed_at = data.get('confirmed_at')
        self.push_sent = data.get('push_sent', False)
        self.device_token = data.get('device_token')
        if self.status == 'STOPPING':
            self.status = 'STOPPED'

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        output = self.snapshot() | {'device_token': self.device_token, 'push_sent': self.push_sent}
        tmp = self.state_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        os.chmod(tmp, 0o600)
        tmp.replace(self.state_file)

    def snapshot(self):
        return {'status': self.status, 'job': self.job, 'last_checked': self.last_checked,
                'last_message': self.last_message, 'error_count': self.error_count,
                'confirmed_at': self.confirmed_at, 'poll_seconds': self.poll_seconds}

    async def run_forever(self):
        # Keep the worker alive across job starts and stops. Checks run only when enabled.
        while True:
            async with self.lock:
                active = self.status == 'WATCHING' and bool(self.job)
                job = dict(self.job) if active else None
            if not active:
                self.wakeup.clear()
                await self.wakeup.wait()
                continue
            deadline = datetime.strptime(f"{job['date']} {job['time']}", '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
            if local_now() >= deadline:
                async with self.lock:
                    if self.status == 'WATCHING':
                        self.status = 'EXPIRED'
                        self.last_message = 'Reservation start time passed'
                        self._save()
                continue
            await self.check_once()
            self.wakeup.clear()
            try:
                await asyncio.wait_for(self.wakeup.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def check_once(self):
        async with self.lock:
            if self.status != 'WATCHING' or not self.job:
                return
            job = dict(self.job)
        try:
            result = await self.checker(job)
        except Exception as e:
            from booking import BookingUncertain, LoginRequired, SetupRequired
            async with self.lock:
                if isinstance(e, BookingUncertain):
                    self.status = 'VERIFY_MANUALLY'
                elif isinstance(e, LoginRequired):
                    self.status = 'LOGIN_REQUIRED'
                elif isinstance(e, SetupRequired):
                    self.status = 'SETUP_REQUIRED'
                else:
                    self.error_count += 1
                    if self.error_count >= 5:
                        self.status = 'ERROR'
                self.last_checked = iso()
                self.last_message = str(e)[:240]
                self._save()
            return
        async with self.lock:
            self.last_checked = iso()
            self.error_count = 0
            if result == 'CONFIRMED':
                self.status = 'CONFIRMED'
                self.confirmed_at = iso()
                self.last_message = 'Reservation verified. Monitoring stopped.'
            else:
                self.last_message = 'Target slot not available; checking again later.'
            self._save()
            should_notify = result == 'CONFIRMED' and not self.push_sent
            token = self.device_token
        if should_notify and token:
            try:
                await self.notifier(token, job)
            except Exception as e:
                async with self.lock:
                    self.last_message += ' Push failed: ' + str(e)[:120]
                    self._save()
            else:
                async with self.lock:
                    self.push_sent = True
                    self._save()

    async def start(self, job: dict):
        async with self.lock:
            if self.status in ('WATCHING', 'STOPPING'):
                raise ValueError('A reservation monitor is already active')
            if self.status == 'CONFIRMED' and self.job == job:
                raise ValueError('This exact reservation was already confirmed. Monitoring not restarted')
            deadline = datetime.strptime(f"{job['date']} {job['time']}", '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
            if deadline <= local_now():
                raise ValueError('The target session must be in the future')
            self.job = job
            self.status = 'WATCHING'
            self.error_count = 0
            self.confirmed_at = None
            self.last_checked = None
            self.push_sent = False
            self.last_message = 'Monitor started. First check pending.'
            self._save()
        self.wakeup.set()

    async def stop(self):
        async with self.lock:
            if self.status == 'WATCHING':
                self.status = 'STOPPED'
                self.last_message = 'Monitoring stopped by user'
                self._save()
        self.wakeup.set()

    async def register_device(self, token: str):
        async with self.lock:
            self.device_token = token
            self._save()
