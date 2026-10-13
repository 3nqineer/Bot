"""Single-user backend API. Run on a trusted PC/server behind HTTPS."""
import asyncio
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from booking import check_and_book, load_site_config, SetupRequired
from worker import ReservationWorker
from notifications import send_push

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DATA = ROOT / 'private_data'
SITE_CONFIG = ROOT / 'site_config.json'
API_KEY = os.getenv('APP_API_KEY', '')

async def do_booking(job):
    return await check_and_book(job, DATA / 'browser_profile', SITE_CONFIG)

worker = ReservationWorker(DATA / 'state.json', do_booking, send_push, 300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # A real secret must be set BEFORE the HTTP service is started.
    if len(API_KEY) < 32 or API_KEY == 'REPLACE_ME':
        raise RuntimeError('Set a random 32+ character APP_API_KEY in backend/.env')
    task = asyncio.create_task(worker.run_forever())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title='ODTU Reservation Mobile API', docs_url=None, redoc_url=None, lifespan=lifespan)

def require_api_key(x_api_key: str = Header(default='')):
    if not API_KEY or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail='Invalid API key')

class Reservation(BaseModel):
    facility: str = Field(min_length=2, max_length=90)
    date: str
    time: str

    @field_validator('date')
    @classmethod
    def valid_date(cls, v):
        datetime.strptime(v, '%Y-%m-%d')
        return v

    @field_validator('time')
    @classmethod
    def valid_time(cls, v):
        datetime.strptime(v, '%H:%M')
        return v

class Device(BaseModel):
    token: str = Field(min_length=50, max_length=4096)

@app.get('/health')
def health():
    return {'ok': True}

@app.get('/status', dependencies=[Depends(require_api_key)])
async def status():
    async with worker.lock:
        return worker.snapshot()

@app.post('/device', dependencies=[Depends(require_api_key)])
async def device(data: Device):
    await worker.register_device(data.token)
    return {'ok': True}

@app.post('/start', dependencies=[Depends(require_api_key)])
async def start(data: Reservation):
    try:
        load_site_config(SITE_CONFIG)
    except (OSError, ValueError, SetupRequired) as exc:
        raise HTTPException(status_code=409, detail=f'Configure booking page first: {exc}')
    if not (DATA / 'browser_profile').exists():
        raise HTTPException(status_code=409, detail='Login on the backend PC using login.py first')
    try:
        await worker.start(data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return worker.snapshot()

@app.post('/stop', dependencies=[Depends(require_api_key)])
async def stop():
    await worker.stop()
    return worker.snapshot()
