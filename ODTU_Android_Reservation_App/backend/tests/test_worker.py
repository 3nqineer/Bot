import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker import ReservationWorker
from booking import LoginRequired, BookingUncertain, SetupRequired, load_site_config


def future_job():
    day = datetime.now(ZoneInfo('Europe/Istanbul')) + timedelta(days=3)
    return {'facility': 'Test facility', 'date': day.strftime('%Y-%m-%d'), 'time': '18:00'}


def test_unavailable_then_confirmed_only_one_push(tmp_path):
    async def run():
        replies = iter(['UNAVAILABLE', 'CONFIRMED', 'CONFIRMED'])
        pushes = []
        async def checker(job):
            return next(replies)
        async def notifier(token, job):
            pushes.append((token, job))
        worker = ReservationWorker(tmp_path / 'state.json', checker, notifier)
        await worker.register_device('test-token')
        await worker.start(future_job())
        await worker.check_once()
        assert worker.status == 'WATCHING'
        await worker.check_once()
        assert worker.status == 'CONFIRMED'
        assert worker.push_sent
        assert len(pushes) == 1
        await worker.check_once()
        assert len(pushes) == 1
        reload = ReservationWorker(tmp_path / 'state.json', checker, notifier)
        assert reload.status == 'CONFIRMED'
        assert reload.push_sent
    asyncio.run(run())


def test_no_booking_when_login_needed(tmp_path):
    async def run():
        async def checker(job):
            raise LoginRequired('manual login required')
        worker = ReservationWorker(tmp_path / 'state.json', checker, lambda *_: None)
        await worker.start(future_job())
        await worker.check_once()
        assert worker.status == 'LOGIN_REQUIRED'
    asyncio.run(run())


def test_uncertain_booking_stops(tmp_path):
    async def run():
        async def checker(job):
            raise BookingUncertain('confirmation unavailable')
        worker = ReservationWorker(tmp_path / 'state.json', checker, lambda *_: None)
        await worker.start(future_job())
        await worker.check_once()
        assert worker.status == 'VERIFY_MANUALLY'
    asyncio.run(run())


def test_manual_stop(tmp_path):
    async def run():
        runs = []
        async def checker(job):
            runs.append(job)
            return 'UNAVAILABLE'
        worker = ReservationWorker(tmp_path / 'state.json', checker, lambda *_: None)
        await worker.start(future_job())
        await worker.stop()
        await worker.check_once()
        assert worker.status == 'STOPPED' and not runs
    asyncio.run(run())


def test_minimum_interval(tmp_path):
    try:
        ReservationWorker(tmp_path / 's.json', None, None, poll_seconds=120)
        assert False
    except ValueError:
        pass


def test_placeholder_site_config_rejected(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'site_config.json'
    try:
        load_site_config(source)
        assert False
    except SetupRequired:
        pass


def test_do_not_restart_confirmed_same_slot(tmp_path):
    async def run():
        async def checker(job):
            return 'CONFIRMED'
        async def notifier(token, job):
            return None
        worker = ReservationWorker(tmp_path / 'state.json', checker, notifier)
        job = future_job()
        await worker.start(job)
        await worker.check_once()
        try:
            await worker.start(job)
            assert False
        except ValueError as exc:
            assert 'already confirmed' in str(exc)
    asyncio.run(run())
