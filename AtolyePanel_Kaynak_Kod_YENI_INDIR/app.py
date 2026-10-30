"""Uçak Bakım Kartı Takip Sistemi — FastAPI + SQLite.

Demo/prototip. Resmî bakım kaydı veya airworthiness release sistemi değildir.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager, asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

BASE = Path(__file__).resolve().parent
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if os.getenv('VERCEL') and not DATABASE_URL:
    raise RuntimeError('Vercel requires a durable external DATABASE_URL. Local SQLite is not allowed.')
try:
    import psycopg
    INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
except ImportError:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)
DB_FILE = Path(os.getenv('TRACKER_DB_PATH', str(BASE / 'data' / 'tracker.sqlite3')))
SECRET_FILE = Path(os.getenv('TRACKER_SECRET_PATH', str(BASE / 'data' / 'session.key')))
ZONE = ZoneInfo('Europe/Istanbul')
LOCATIONS = ('ISL1', 'ISL2', 'IST', 'SAW')
TR_MONTHS = ('', 'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık')
TR_WEEKDAYS = ('Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz')
STATUS = {
    'planned': 'Planlandı', 'received': 'Atölyeye geldi',
    'in_progress': 'İşlemde', 'on_hold': 'Beklemede', 'completed': 'Tamamlandı',
}


def now():
    return datetime.now(ZONE).strftime('%Y-%m-%d %H:%M:%S')


def today():
    return datetime.now(ZONE).date().isoformat()


def get_secret():
    supplied = os.getenv('TRACKER_SESSION_SECRET', '').strip()
    if supplied and len(supplied) >= 32:
        return supplied
    if DATABASE_URL or os.getenv('VERCEL'):
        raise RuntimeError('TRACKER_SESSION_SECRET must be a stable secret of 32+ chars in cloud hosting.')
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding='utf-8').strip()
    key = secrets.token_hex(32)
    try:
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(key)
        return key
    except FileExistsError:
        return SECRET_FILE.read_text(encoding='utf-8').strip()


@contextmanager
def conn():
    if DATABASE_URL:
        from db_backend import PgConnection
        db = PgConnection(DATABASE_URL)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_FILE, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 15000')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    if DATABASE_URL:
        from db_backend import init_postgres
        return init_postgres(conn)
    with conn() as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin','technician')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS aircraft (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registration TEXT NOT NULL UNIQUE COLLATE NOCASE,
            aircraft_model TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aircraft_id INTEGER NOT NULL REFERENCES aircraft(id),
            card_code TEXT NOT NULL,
            title TEXT NOT NULL,
            planned_date TEXT NOT NULL,
            planned_time TEXT NOT NULL DEFAULT '',
            workshop TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','received','in_progress','on_hold','completed')),
            actual_received_at TEXT,
            latest_note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            updated_by INTEGER REFERENCES users(id),
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS card_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL REFERENCES cards(id),
            user_id INTEGER REFERENCES users(id),
            event_type TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT,
            note TEXT NOT NULL DEFAULT '',
            recorded_received_at TEXT,
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_cards_aircraft ON cards(aircraft_id);
        CREATE INDEX IF NOT EXISTS ix_cards_planned ON cards(planned_date);
        CREATE INDEX IF NOT EXISTS ix_events_card ON card_events(card_id, id DESC);
        ''')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(cards)')}
        for name, sql_type in (
            ('actual_completed_at', 'TEXT'),
            ('assigned_to', 'INTEGER REFERENCES users(id)'),
            ('assigned_at', 'TEXT'),
            ('assigned_by', 'INTEGER REFERENCES users(id)'),
            ('latest_note_by', 'INTEGER REFERENCES users(id)'),
            ('latest_note_at', 'TEXT'),
        ):
            if name not in columns:
                db.execute(f'ALTER TABLE cards ADD COLUMN {name} {sql_type}')
        # For V1/V2 existing notes, preserve the last known note provenance on migration.
        db.execute('''UPDATE cards SET latest_note_by=updated_by,latest_note_at=updated_at
                      WHERE latest_note <> '' AND latest_note_at IS NULL''')
        event_cols = {r['name'] for r in db.execute('PRAGMA table_info(card_events)')}
        for name, sql_type in (
            ('from_assignee_id', 'INTEGER REFERENCES users(id)'),
            ('to_assignee_id', 'INTEGER REFERENCES users(id)'),
            ('shift_name', 'TEXT'),
        ):
            if name not in event_cols:
                db.execute(f'ALTER TABLE card_events ADD COLUMN {name} {sql_type}')
        db.execute('CREATE INDEX IF NOT EXISTS ix_cards_assigned_to ON cards(assigned_to, status)')
        db.execute('CREATE INDEX IF NOT EXISTS ix_events_type_date ON card_events(event_type, occurred_at)')


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 400_000)
    return f'pbkdf2_sha256$400000${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        method, iters, salt, digest = stored.split('$')
        if method != 'pbkdf2_sha256':
            return False
        test = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(test, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def valid_password(password: str):
    if len(password) < 10 or len(password) > 128:
        raise ValueError('Şifre 10–128 karakter olmalıdır.')


def clean(value: str, maximum=140, required=True):
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise ValueError(f'Bu alan gerekli ve en fazla {maximum} karakter olabilir.')
    return value


def check_date(value: str):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError('Geçerli bir planlanan tarih giriniz.')


def check_time(value: str):
    value = value.strip()
    if value:
        if not re.fullmatch(r'\d{2}:\d{2}', value):
            raise ValueError('Saat SS:DD biçiminde olmalıdır.')
        try:
            datetime.strptime(value, '%H:%M')
        except ValueError:
            raise ValueError('Geçerli saat giriniz.')
    return value


def validate_assignee(db, assignee_id):
    if assignee_id is None or assignee_id == '':
        return None
    try:
        uid = int(assignee_id)
    except (ValueError, TypeError):
        raise ValueError('Geçerli bir teknisyen seçiniz.')
    row = db.execute('SELECT id,full_name,active,role FROM users WHERE id=?', (uid,)).fetchone()
    if not row or row['role'] != 'technician' or not row['active']:
        raise ValueError('Yalnızca aktif teknisyenlere görev atanabilir.')
    return row


def record_assignment(db, *, card_id, actor_id, previous, target, event_type, note='', shift=''):
    old_id = previous['id'] if previous else None
    new_id = target['id'] if target else None
    old_name = previous['full_name'] if previous else 'Atanmamış'
    new_name = target['full_name'] if target else 'Atanmamış'
    description = f'Sorumlu: {old_name} → {new_name}'
    if shift:
        description += f' | Devir vardiyası: {shift}'
    if note:
        description += f'\nAçıklama: {note}'
    db.execute('''UPDATE cards SET assigned_to=?,assigned_at=?,assigned_by=?,updated_at=?,updated_by=? WHERE id=?''',
               (new_id, now() if target else None, actor_id, now(), actor_id, card_id))
    db.execute('''INSERT INTO card_events(card_id,user_id,event_type,note,from_assignee_id,to_assignee_id,shift_name,occurred_at)
                  VALUES(?,?,?,?,?,?,?,?)''',
               (card_id, actor_id, event_type, description, old_id, new_id, shift, now()))


def current_assignee(db, card):
    if card['assigned_to'] is None:
        return None
    return db.execute('SELECT id,full_name FROM users WHERE id=?', (card['assigned_to'],)).fetchone()


def received_datetime(value: str):
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
        if parsed.tzinfo:
            raise ValueError
        if parsed > datetime.now(ZONE).replace(tzinfo=None) + timedelta(minutes=10):
            raise ValueError('Geliş zamanı gelecekte olamaz.')
        return parsed.strftime('%Y-%m-%d %H:%M')
    except ValueError as exc:
        if 'gelecekte' in str(exc):
            raise
        raise ValueError('Geliş tarihi ve saatini kontrol ediniz.')


@asynccontextmanager
async def lifespan(application):
    init_db()
    yield


app = FastAPI(title='Uçak Bakım Kartı Takip', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=get_secret(), max_age=12*3600,
                   same_site='lax', https_only=os.getenv('SECURE_COOKIES') == '1' or bool(os.getenv('VERCEL')))
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
templates = Jinja2Templates(directory=str(BASE / 'templates'))
templates.env.globals['STATUS'] = STATUS
templates.env.globals['LOCATIONS'] = LOCATIONS


def redirect(path):
    return RedirectResponse(path, status_code=303)


def flash(request, message, category='info'):
    request.session['flash'] = {'message': str(message), 'category': category}


def render(request, name, **context):
    user = current_user(request)
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_urlsafe(32)
    return templates.TemplateResponse(request, name, {
        'user': user, 'csrf': request.session['csrf'],
        'flash': request.session.pop('flash', None), 'today': today(),
        'now_local': now(), **context,
    })


def current_user(request):
    uid = request.session.get('uid')
    if not uid:
        return None
    with conn() as db:
        row = db.execute('SELECT id,username,full_name,role,active FROM users WHERE id=?', (uid,)).fetchone()
    if not row or not row['active']:
        request.session.clear()
        return None
    return dict(row)


def must_login(request, admin=False):
    user = current_user(request)
    if not user:
        raise HTTPException(401, 'Oturum açmanız gerekiyor.')
    if admin and user['role'] != 'admin':
        raise HTTPException(403, 'Bu işlem yalnızca yönetici tarafından yapılabilir.')
    return user


def csrf_check(request, token):
    expected = request.session.get('csrf')
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(403, 'Güvenlik doğrulaması başarısız. Sayfayı yenileyiniz.')


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    if exc.status_code == 401:
        return redirect('/login')
    return HTMLResponse(f'<h2>İşlem gerçekleştirilemedi ({exc.status_code})</h2>'
                        '<p>Yetki veya oturum bilgilerinizi kontrol edin.</p><a href="/">Ana sayfa</a>',
                        status_code=exc.status_code)


@app.get('/')
def root(request: Request):
    return redirect('/dashboard' if current_user(request) else '/login')


@app.get('/login')
def login_page(request: Request):
    if current_user(request):
        return redirect('/dashboard')
    return render(request, 'login.html')


# Minimal in-memory protection against repeated login attempts; reverse proxy may need extra rules.
LOGIN_FAILURES = {}


@app.post('/login')
def login(request: Request, username: str = Form(''), password: str = Form(''), csrf: str = Form('')):
    csrf_check(request, csrf)
    key = (request.client.host if request.client else 'unknown', username.lower().strip())
    events = [time for time in LOGIN_FAILURES.get(key, []) if datetime.now().timestamp() - time < 900]
    if len(events) >= 8:
        flash(request, 'Çok sayıda başarısız deneme. 15 dakika sonra tekrar deneyiniz.', 'error')
        return redirect('/login')
    with conn() as db:
        row = db.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (username.strip(),)).fetchone()
    if not row or not row['active'] or not verify_password(password, row['password_hash']):
        events.append(datetime.now().timestamp())
        LOGIN_FAILURES[key] = events
        flash(request, 'Kullanıcı adı veya şifre hatalı.', 'error')
        return redirect('/login')
    LOGIN_FAILURES.pop(key, None)
    request.session.clear()
    request.session['uid'] = row['id']
    request.session['csrf'] = secrets.token_urlsafe(32)
    flash(request, 'Hoş geldiniz, ' + row['full_name'] + '.')
    return redirect('/dashboard')


@app.post('/logout')
def logout(request: Request, csrf: str = Form('')):
    csrf_check(request, csrf)
    request.session.clear()
    return redirect('/login')


def load_cards(db):
    rows = db.execute('''
      SELECT c.*,a.registration,a.aircraft_model,u.full_name AS updated_by_name,
             owner.full_name AS assignee_name, owner.active AS assignee_active,
             note_user.full_name AS last_note_by_name
      FROM cards c JOIN aircraft a ON a.id=c.aircraft_id
      LEFT JOIN users u ON u.id=c.updated_by
      LEFT JOIN users owner ON owner.id=c.assigned_to
      LEFT JOIN users note_user ON note_user.id=c.latest_note_by
      ORDER BY c.planned_date ASC, c.planned_time ASC, c.id DESC
    ''').fetchall()
    return [card_view(dict(r)) for r in rows]


def card_view(card):
    card['overdue'] = (card['planned_date'] < today() and
                       not card['actual_received_at'] and card['status'] != 'completed')
    card['due_today'] = card['planned_date'] == today() and not card['actual_received_at']
    card['received_today'] = bool(card['actual_received_at'] and card['actual_received_at'][:10] == today())
    card['status_name'] = STATUS.get(card['status'], card['status'])
    return card


def build_calendar(cards, *, month_value: str, day_value: str, location: str, path: str):
    """Build a server-rendered, clickable Turkish calendar for planned ARRIVALS only."""
    current = datetime.now(ZONE).date()
    if re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month_value or ''):
        try:
            first = date.fromisoformat(month_value + '-01')
        except ValueError:
            first = current.replace(day=1)
    else:
        first = current.replace(day=1)
    if not 2020 <= first.year <= 2100:
        first = current.replace(day=1)
    try:
        chosen = date.fromisoformat(day_value)
    except (ValueError, TypeError):
        chosen = current if first.year == current.year and first.month == current.month else first
    if (chosen.year, chosen.month) != (first.year, first.month):
        chosen = current if first.year == current.year and first.month == current.month else first
    selected_day = chosen.isoformat()
    counts = {}
    samples = {}
    for c in sorted(cards, key=lambda c: (c['planned_date'], c['planned_time'], c['card_code'])):
        counts[c['planned_date']] = counts.get(c['planned_date'], 0) + 1
        if len(samples.get(c['planned_date'], [])) < 2:
            samples.setdefault(c['planned_date'], []).append(c['card_code'])
    def url(target_month, target_day):
        params = {'month': target_month, 'day': target_day}
        if location:
            params['location'] = location
        return path + '?' + urlencode(params)
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month):
        items = []
        for d in week:
            ds = d.isoformat()
            items.append({'date': ds, 'day': d.day, 'count': counts.get(ds, 0),
                          'in_month': d.month == first.month, 'selected': ds == selected_day,
                          'samples': samples.get(ds, []),
                          'today': d == current,
                          'url': url(f'{d.year:04d}-{d.month:02d}', ds)})
        weeks.append(items)
    prev = first - timedelta(days=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_string = first.strftime('%Y-%m')
    return {
        'weeks': weeks, 'month_label': TR_MONTHS[first.month] + ' ' + str(first.year),
        'weekdays': TR_WEEKDAYS, 'month_value': month_string,
        'prev_url': url(prev.strftime('%Y-%m'), prev.replace(day=1).isoformat()),
        'next_url': url(nxt.strftime('%Y-%m'), nxt.isoformat()),
        'today_url': url(current.strftime('%Y-%m'), current.isoformat()),
        'selected_day': selected_day,
        'selected_day_label': f'{chosen.day} {TR_MONTHS[chosen.month]} {chosen.year}',
        'day_cards': sorted((c for c in cards if c['planned_date'] == selected_day),
                            key=lambda c: (c['planned_time'], c['registration'], c['card_code'])),
    }


@app.get('/dashboard')
@app.get('/my-tasks')
def dashboard(request: Request, q: str = '', status: str = '', aircraft: str = '', assignee: str = '',
              month: str = '', day: str = '', location: str = ''):
    user = must_login(request)
    is_my_tasks = request.url.path == '/my-tasks'
    if is_my_tasks:
        assignee = 'me'
    with conn() as db:
        all_cards = load_cards(db)
        airplanes = [dict(r) for r in db.execute('SELECT * FROM aircraft ORDER BY registration').fetchall()]
        technicians = [dict(r) for r in db.execute("SELECT id,full_name,active FROM users WHERE role='technician' ORDER BY full_name")]
    if location not in LOCATIONS:
        location = ''
    calendar_cards = [c for c in all_cards if not location or c['workshop'] == location]
    if is_my_tasks:
        calendar_cards = [c for c in calendar_cards if c['assigned_to'] == user['id']]
    cal = build_calendar(calendar_cards, month_value=month, day_value=day,
                         location=location, path=request.url.path)
    q = q.strip()[:80]
    filtered = [c for c in all_cards if not location or c['workshop'] == location]
    if assignee == 'me':
        filtered = [c for c in filtered if c['assigned_to'] == user['id']]
    elif assignee == 'unassigned':
        filtered = [c for c in filtered if c['assigned_to'] is None]
    elif assignee.isdigit():
        filtered = [c for c in filtered if c['assigned_to'] == int(assignee)]
    if q:
        term = q.casefold()
        filtered = [c for c in filtered if term in (' '.join((c['registration'], c['card_code'], c['title'], c['workshop'], c['latest_note']))).casefold()]
    if status == 'overdue':
        filtered = [c for c in filtered if c['overdue']]
    elif status in STATUS:
        filtered = [c for c in filtered if c['status'] == status]
    if aircraft.isdigit():
        filtered = [c for c in filtered if c['aircraft_id'] == int(aircraft)]
    stats = {
        'total': len(all_cards),
        'today': sum(c['due_today'] for c in all_cards),
        'overdue': sum(c['overdue'] for c in all_cards),
        'received_today': sum(c['received_today'] for c in all_cards),
        'in_progress': sum(c['status'] == 'in_progress' for c in all_cards),
        'on_hold': sum(c['status'] == 'on_hold' for c in all_cards),
        'completed': sum(c['status'] == 'completed' for c in all_cards),
        'unassigned_open': sum(c['assigned_to'] is None and c['status'] != 'completed' for c in all_cards),
        'mine_open': sum(c['assigned_to'] == user['id'] and c['status'] != 'completed' for c in all_cards),
    }
    return render(request, 'dashboard.html', cards=filtered, stats=stats, airplanes=airplanes,
                  q=q, selected_status=status, selected_aircraft=aircraft, selected_assignee=assignee,
                  technicians=technicians, is_my_tasks=is_my_tasks, cal=cal, location=location)


def get_card_or_404(db, card_id):
    row = db.execute('''SELECT c.*,a.registration,a.aircraft_model,u.full_name AS updated_by_name,
             owner.full_name AS assignee_name,owner.active AS assignee_active,
             note_user.full_name AS last_note_by_name
             FROM cards c JOIN aircraft a ON a.id=c.aircraft_id
             LEFT JOIN users u ON u.id=c.updated_by
             LEFT JOIN users owner ON owner.id=c.assigned_to
             LEFT JOIN users note_user ON note_user.id=c.latest_note_by WHERE c.id=?''', (card_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Kart bulunamadı.')
    return card_view(dict(row))


@app.get('/cards/new')
def new_card(request: Request, date: str = '', location: str = ''):
    must_login(request, admin=True)
    with conn() as db:
        airplanes = [dict(r) for r in db.execute('SELECT * FROM aircraft ORDER BY registration')]
        technicians = [dict(r) for r in db.execute("SELECT id,full_name FROM users WHERE role='technician' AND active=1 ORDER BY full_name")]
    date_prefill = date if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) else today()
    try:
        date_prefill = check_date(date_prefill)
    except ValueError:
        date_prefill = today()
    return render(request, 'card_form.html', card=None, airplanes=airplanes, technicians=technicians,
                  heading='Yeni bakım kartı', date_prefill=date_prefill, location_prefill=location if location in LOCATIONS else '')


@app.post('/cards/new')
def save_new_card(request: Request, aircraft_id: int = Form(...), card_code: str = Form(''),
                  title: str = Form(''), planned_date: str = Form(''), planned_time: str = Form(''),
                  workshop: str = Form(''), assigned_to: str = Form(''), csrf: str = Form('')):
    user = must_login(request, admin=True)
    csrf_check(request, csrf)
    try:
        card_code, title = clean(card_code, 60), clean(title, 180)
        planned_date, planned_time = check_date(planned_date), check_time(planned_time)
        if workshop not in LOCATIONS:
            raise ValueError('Bakım lokasyonu ISL1, ISL2, IST veya SAW olmalıdır.')
        with conn() as db:
            if not db.execute('SELECT 1 FROM aircraft WHERE id=?', (aircraft_id,)).fetchone():
                raise ValueError('Önce geçerli bir uçak seçiniz.')
            assigned_user = validate_assignee(db, assigned_to)
            cursor = db.execute('''INSERT INTO cards(aircraft_id,card_code,title,planned_date,planned_time,workshop,
                                status,updated_at,updated_by,created_at,created_by)
                    VALUES(?,?,?,?,?,?,'planned',?,?,?,?)''',
                    (aircraft_id, card_code, title, planned_date, planned_time, workshop,
                     now(), user['id'], now(), user['id']))
            card_id = cursor.lastrowid
            db.execute('''INSERT INTO card_events(card_id,user_id,event_type,new_status,note,occurred_at)
                       VALUES(?,?,'Kart oluşturuldu','planned',?,?)''',
                       (card_id, user['id'], f'Planlanan geliş: {planned_date} {planned_time}'.strip(), now()))
            if assigned_user:
                record_assignment(db, card_id=card_id, actor_id=user['id'],previous=None,
                                  target=assigned_user,event_type='Sorumlu atandı',note='Kart oluşturulurken atandı')
        flash(request, 'Bakım kartı oluşturuldu.', 'success')
        return redirect(f'/cards/{card_id}')
    except ValueError as exc:
        flash(request, str(exc), 'error')
        return redirect('/cards/new')


@app.get('/cards/{card_id}/edit')
def edit_card(request: Request, card_id: int):
    must_login(request, admin=True)
    with conn() as db:
        card = get_card_or_404(db, card_id)
        airplanes = [dict(r) for r in db.execute('SELECT * FROM aircraft ORDER BY registration')]
    return render(request, 'card_form.html', card=card, airplanes=airplanes, heading='Kart planını düzenle')


@app.post('/cards/{card_id}/edit')
def save_card_edit(request: Request, card_id: int, aircraft_id: int = Form(...), card_code: str = Form(''),
                   title: str = Form(''), planned_date: str = Form(''), planned_time: str = Form(''),
                   workshop: str = Form(''), reason: str = Form(''), csrf: str = Form('')):
    user = must_login(request, admin=True)
    csrf_check(request, csrf)
    try:
        card_code, title = clean(card_code, 60), clean(title, 180)
        planned_date, planned_time = check_date(planned_date), check_time(planned_time)
        if workshop not in LOCATIONS:
            raise ValueError('Bakım lokasyonu ISL1, ISL2, IST veya SAW olmalıdır.')
        reason = clean(reason, 1000)
        with conn() as db:
            old = get_card_or_404(db, card_id)
            if not db.execute('SELECT 1 FROM aircraft WHERE id=?', (aircraft_id,)).fetchone():
                raise ValueError('Uçak geçersiz.')
            db.execute('''UPDATE cards SET aircraft_id=?,card_code=?,title=?,planned_date=?,planned_time=?,workshop=?,
                       updated_at=?,updated_by=? WHERE id=?''',
                       (aircraft_id, card_code, title, planned_date, planned_time, workshop, now(), user['id'],card_id))
            db.execute('''INSERT INTO card_events(card_id,user_id,event_type,old_status,new_status,note,occurred_at)
                       VALUES(?,?,'Plan değiştirildi',?,?,?,?)''',
                       (card_id,user['id'],old['status'],old['status'],
                        f'{reason} | Eski plan: {old["registration"]} / {old["card_code"]} / {old["planned_date"]} {old["planned_time"]}',now()))
        flash(request, 'Kart planı güncellendi.', 'success')
        return redirect(f'/cards/{card_id}')
    except ValueError as exc:
        flash(request, str(exc), 'error')
        return redirect(f'/cards/{card_id}/edit')


@app.get('/cards/{card_id}')
def card_detail(request: Request, card_id: int):
    must_login(request)
    with conn() as db:
        card = get_card_or_404(db, card_id)
        history = [dict(row) for row in db.execute('''SELECT e.*,u.full_name AS actor
                     FROM card_events e LEFT JOIN users u ON u.id=e.user_id
                     WHERE card_id=? ORDER BY e.id DESC''',(card_id,))]
        technicians = [dict(r) for r in db.execute("SELECT id,full_name FROM users WHERE role='technician' AND active=1 ORDER BY full_name")]
    user = must_login(request)
    can_update = user['role'] == 'admin' or card['assigned_to'] in (None, user['id'])
    can_handover = card['status'] != 'completed' and (user['role'] == 'admin' or card['assigned_to'] == user['id']) and card['assigned_to'] is not None
    return render(request, 'card_detail.html', card=card, history=history, technicians=technicians,
                  can_update=can_update, can_handover=can_handover,
                  current_datetime=datetime.now(ZONE).strftime('%Y-%m-%dT%H:%M'))


@app.post('/cards/{card_id}/update')
def update_card(request: Request, card_id: int, status: str = Form(''),
                note: str = Form(''), actual_received_at: str = Form(''),
                actual_completed_at: str = Form(''), csrf: str = Form('')):
    user = must_login(request)
    csrf_check(request, csrf)
    try:
        if status not in STATUS:
            raise ValueError('Geçerli durum seçiniz.')
        note = clean(note, 2500, required=False)
        received = received_datetime(actual_received_at)
        with conn() as db:
            db.execute('BEGIN IMMEDIATE')  # Assign / update atomically against simultaneous users.
            old = get_card_or_404(db, card_id)
            if user['role'] != 'admin' and old['assigned_to'] not in (None, user['id']):
                raise HTTPException(403, 'Bu kart başka bir teknisyene atanmış.')
            if old['actual_received_at'] and received and old['actual_received_at'] != received:
                if user['role'] != 'admin':
                    raise ValueError('Geliş zamanı yalnızca yönetici tarafından düzeltilebilir.')
                if not note:
                    raise ValueError('Geliş zamanını düzeltmek için açıklama yazınız.')
            received = received or old['actual_received_at']
            completed = received_datetime(actual_completed_at)
            if old['actual_completed_at'] and completed and completed != old['actual_completed_at']:
                if user['role'] != 'admin':
                    raise ValueError('Bitiş zamanı yalnızca yönetici tarafından düzeltilebilir.')
                if not note:
                    raise ValueError('Bitiş zamanını düzeltmek için açıklama yazınız.')
            completed = completed or old['actual_completed_at']
            if status == 'completed' and not completed:
                completed = now()
            if status == 'completed' and not received:
                raise ValueError('Kart tamamlanmadan önce geliş tarihi/saatini kaydediniz.')
            if completed and received and completed < received:
                raise ValueError('Bitiş zamanı geliş zamanından önce olamaz.')
            status_changed = status != old['status']
            completed_changed = completed != old['actual_completed_at']
            received_changed = received != old['actual_received_at']
            if not (status_changed or received_changed or completed_changed or note):
                raise ValueError('Kaydetmek için en az bir değişiklik veya bilgi notu giriniz.')
            if old['assigned_to'] is None and user['role'] == 'technician':
                owner = validate_assignee(db, user['id'])
                record_assignment(db, card_id=card_id, actor_id=user['id'],previous=None,
                                  target=owner,event_type='Görev devralındı',note='İlk kart güncellemesiyle sorumluluk alındı')
            latest_note = note if note else old['latest_note']
            db.execute('''UPDATE cards SET status=?,actual_received_at=?,actual_completed_at=?,latest_note=?,
                        latest_note_by=CASE WHEN ? THEN ? ELSE latest_note_by END,
                        latest_note_at=CASE WHEN ? THEN ? ELSE latest_note_at END,
                        updated_at=?,updated_by=? WHERE id=?''',
                       (status, received, completed, latest_note, bool(note), user['id'],
                        bool(note), now(), now(), user['id'], card_id))
            parts=[]
            if received_changed:
                parts.append(('Geliş zamanı düzeltildi' if old['actual_received_at'] else 'Kart atölyeye geldi') + f': {received}')
            if completed_changed:
                parts.append(f'Bitiş zamanı kaydedildi: {completed}')
            if status_changed:
                parts.append(f'Durum: {STATUS[old["status"]]} → {STATUS[status]}')
            if note:
                parts.append(note)
            event_type = 'Bitiş kaydı' if completed_changed else ('Geliş kaydı' if received_changed else ('Durum değişikliği' if status_changed else 'Teknisyen yorumu'))
            db.execute('''INSERT INTO card_events(card_id,user_id,event_type,old_status,new_status,note,
                         recorded_received_at,occurred_at) VALUES(?,?,?,?,?,?,?,?)''',
                       (card_id,user['id'],event_type,old['status'],status,'\n'.join(parts),received if received_changed else None,now()))
        flash(request, 'Kart bilgisi ve işlem geçmişi güncellendi.', 'success')
        return redirect(f'/cards/{card_id}')
    except ValueError as exc:
        flash(request, str(exc), 'error')
        return redirect(f'/cards/{card_id}')


@app.post('/cards/{card_id}/claim')
def claim_card(request: Request, card_id: int, csrf: str = Form('')):
    user = must_login(request)
    csrf_check(request, csrf)
    with conn() as db:
        db.execute('BEGIN IMMEDIATE')
        card = get_card_or_404(db, card_id)
        if card['status'] == 'completed' or card['assigned_to'] is not None:
            flash(request, 'Bu kart boşta değil veya tamamlanmış.', 'error')
            return redirect(f'/cards/{card_id}')
        owner = validate_assignee(db, user['id']) if user['role'] == 'technician' else None
        if not owner:
            flash(request, 'Yönetici olarak kartı üstlenmek yerine teknisyen atayınız.', 'error')
            return redirect(f'/cards/{card_id}')
        record_assignment(db, card_id=card_id, actor_id=user['id'], previous=None,
                          target=owner, event_type='Görev devralındı', note='Teknisyen tarafından üstlenildi')
    flash(request, 'Kart sorumluluğunu üstlendiniz.', 'success')
    return redirect(f'/cards/{card_id}')


@app.post('/cards/{card_id}/assign')
def assign_card(request: Request, card_id: int, assignee_id: str = Form(''),
                reason: str = Form(''), csrf: str = Form('')):
    user = must_login(request, admin=True)
    csrf_check(request, csrf)
    try:
        reason = clean(reason, 1000, required=False)
        with conn() as db:
            db.execute('BEGIN IMMEDIATE')
            card = get_card_or_404(db, card_id)
            if card['status'] == 'completed':
                raise ValueError('Tamamlanan kartın sorumlusu değiştirilemez.')
            target = validate_assignee(db, assignee_id)
            if card['assigned_to'] == (target['id'] if target else None):
                raise ValueError('Sorumlu teknisyen zaten bu şekilde kayıtlı.')
            if card['assigned_to'] is not None and not reason:
                raise ValueError('Mevcut sorumlu değiştiriliyorsa gerekçe zorunludur.')
            previous = current_assignee(db, card)
            record_assignment(db, card_id=card_id, actor_id=user['id'],previous=previous,
                              target=target,event_type='Sorumlu değiştirildi' if previous else 'Sorumlu atandı',note=reason)
        flash(request, 'Kart sorumlusu kaydedildi.', 'success')
    except ValueError as exc:
        flash(request, str(exc), 'error')
    return redirect(f'/cards/{card_id}')


SHIFT_NAMES = ('Sabah', 'Akşam', 'Gece', 'Diğer')


@app.post('/cards/{card_id}/handover')
def handover_card(request: Request, card_id: int, to_user_id: int = Form(...),
                  shift_name: str = Form(''), note: str = Form(''), csrf: str = Form('')):
    user = must_login(request)
    csrf_check(request, csrf)
    try:
        note = clean(note, 1500)
        if len(note) < 8:
            raise ValueError('Vardiya devri için en az 8 karakterlik bilgi notu yazınız.')
        if shift_name not in SHIFT_NAMES:
            raise ValueError('Devredilen vardiyayı seçiniz.')
        with conn() as db:
            db.execute('BEGIN IMMEDIATE')
            card = get_card_or_404(db, card_id)
            if card['status'] == 'completed':
                raise ValueError('Tamamlanan kartlar devredilemez.')
            if card['assigned_to'] is None:
                raise ValueError('Önce kartın bir sorumlusu olmalıdır.')
            if user['role'] != 'admin' and card['assigned_to'] != user['id']:
                raise HTTPException(403, 'Yalnızca sorumlu teknisyen veya yönetici devredebilir.')
            target = validate_assignee(db, to_user_id)
            if target['id'] == card['assigned_to']:
                raise ValueError('Görevi aynı teknisyene devredemezsiniz.')
            previous = current_assignee(db, card)
            record_assignment(db,card_id=card_id,actor_id=user['id'], previous=previous,
                              target=target,event_type='Vardiya devri',note=note,shift=shift_name)
        flash(request, f'Görev {target["full_name"]} adlı teknisyene devredildi.', 'success')
    except ValueError as exc:
        flash(request, str(exc), 'error')
    return redirect(f'/cards/{card_id}')


@app.get('/assignments')
def assignments_page(request: Request):
    must_login(request)
    with conn() as db:
        techs = [dict(r) for r in db.execute('''SELECT u.id,u.full_name,u.username,u.active,
            COUNT(c.id) AS total_cards,
            SUM(CASE WHEN c.id IS NOT NULL AND c.status <> 'completed' THEN 1 ELSE 0 END) AS open_cards,
            SUM(CASE WHEN c.status='in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN c.status='on_hold' THEN 1 ELSE 0 END) AS on_hold
            FROM users u LEFT JOIN cards c ON c.assigned_to=u.id
            WHERE u.role='technician' GROUP BY u.id ORDER BY open_cards DESC,u.full_name''')]
        unassigned = [c for c in load_cards(db) if c['assigned_to'] is None and c['status']!='completed']
        handovers = [dict(r) for r in db.execute('''SELECT e.*,c.card_code,a.registration,
            actor.full_name AS actor_name,from_u.full_name AS from_name,to_u.full_name AS to_name
            FROM card_events e JOIN cards c ON c.id=e.card_id JOIN aircraft a ON a.id=c.aircraft_id
            LEFT JOIN users actor ON actor.id=e.user_id
            LEFT JOIN users from_u ON from_u.id=e.from_assignee_id
            LEFT JOIN users to_u ON to_u.id=e.to_assignee_id
            WHERE e.event_type='Vardiya devri' ORDER BY e.id DESC LIMIT 30''')]
    return render(request, 'assignments.html', technicians=techs, unassigned=unassigned, handovers=handovers)


@app.get('/aircraft')
def aircraft_page(request: Request):
    must_login(request, admin=True)
    with conn() as db:
        airplanes = [dict(r) for r in db.execute('''SELECT a.*,count(c.id) AS card_count
                    FROM aircraft a LEFT JOIN cards c ON c.aircraft_id=a.id
                    GROUP BY a.id ORDER BY a.registration''')]
    return render(request,'aircraft.html',airplanes=airplanes)


@app.post('/aircraft')
def add_aircraft(request: Request, registration: str = Form(''),
                 aircraft_model: str = Form(''), csrf: str = Form('')):
    must_login(request, admin=True)
    csrf_check(request, csrf)
    try:
        registration = clean(registration.upper(), 30)
        aircraft_model = clean(aircraft_model, 100, required=False)
        with conn() as db:
            db.execute('INSERT INTO aircraft(registration,aircraft_model,created_at) VALUES(?,?,?)',
                       (registration,aircraft_model,now()))
        flash(request,'Uçak eklendi.','success')
    except INTEGRITY_ERRORS:
        flash(request,'Bu uçak kaydı zaten var.','error')
    except ValueError as exc:
        flash(request,str(exc),'error')
    return redirect('/aircraft')


@app.get('/users')
def users_page(request: Request):
    must_login(request, admin=True)
    with conn() as db:
        users = [dict(row) for row in db.execute('''SELECT u.id,u.username,u.full_name,u.role,u.active,u.created_at,
                    COUNT(CASE WHEN c.status <> 'completed' THEN 1 END) AS open_cards
                    FROM users u LEFT JOIN cards c ON c.assigned_to=u.id
                    GROUP BY u.id ORDER BY u.role,u.full_name''')]
    return render(request,'users.html',users=users)


@app.post('/users')
def add_user(request: Request, username: str = Form(''), full_name: str = Form(''),
             password: str = Form(''), role: str = Form('technician'), csrf: str = Form('')):
    must_login(request, admin=True)
    csrf_check(request, csrf)
    try:
        username = clean(username, 50)
        full_name = clean(full_name, 100)
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', username):
            raise ValueError('Kullanıcı adında yalnızca harf, sayı, nokta, tire ve alt çizgi kullanılabilir.')
        if role not in ('technician','admin'):
            raise ValueError('Geçersiz kullanıcı rolü.')
        valid_password(password)
        with conn() as db:
            db.execute('''INSERT INTO users(username,full_name,password_hash,role,active,created_at)
                          VALUES(?,?,?,?,1,?)''',(username,full_name,hash_password(password),role,now()))
        flash(request,'Kullanıcı oluşturuldu.','success')
    except INTEGRITY_ERRORS:
        flash(request,'Bu kullanıcı adı zaten kullanılıyor.','error')
    except ValueError as exc:
        flash(request,str(exc),'error')
    return redirect('/users')


@app.post('/users/{user_id}/reset-password')
def reset_user_password(request: Request, user_id: int, new_password: str = Form(''), csrf: str = Form('')):
    must_login(request, admin=True)
    csrf_check(request, csrf)
    try:
        valid_password(new_password)
        with conn() as db:
            exists = db.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone()
            if not exists:
                raise HTTPException(404, 'Kullanıcı bulunamadı.')
            db.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(new_password), user_id))
        flash(request, 'Kullanıcı parolası yenilendi.', 'success')
    except ValueError as exc:
        flash(request, str(exc), 'error')
    return redirect('/users')


@app.post('/users/{user_id}/toggle')
def toggle_user(request: Request, user_id: int, csrf: str = Form('')):
    admin = must_login(request, admin=True)
    csrf_check(request, csrf)
    if user_id == admin['id']:
        flash(request,'Kendi hesabınızı pasifleştiremezsiniz.','error')
        return redirect('/users')
    with conn() as db:
        subject = db.execute('SELECT id,role,active FROM users WHERE id=?',(user_id,)).fetchone()
        if not subject:
            raise HTTPException(404, 'Kullanıcı bulunamadı.')
        if subject['role']=='admin' and subject['active']:
            active_admins = db.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            if active_admins <= 1:
                flash(request,'Son aktif yönetici pasifleştirilemez.','error')
                return redirect('/users')
        db.execute('UPDATE users SET active=? WHERE id=?',(0 if subject['active'] else 1,user_id))
    flash(request,'Kullanıcı durumu değiştirildi.','success')
    return redirect('/users')


@app.get('/export.csv')
def export_csv(request: Request):
    must_login(request, admin=True)
    with conn() as db:
        cards = load_cards(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Uçak','Model','Kart kodu','Kart adı','Plan tarihi','Plan saati','Atölye',
                     'Durum','Gerçek geliş tarihi/saati','Gerçek bitiş tarihi/saati','Sorumlu teknisyen',
                     'Sorumlu atama zamanı','Son açıklama','Son güncelleyen','Son güncelleme'])
    for c in cards:
        # Prevent spreadsheet formula injection on user-controlled text.
        def safe(value):
            value = str(value or '')
            return "'" + value if value and value.lstrip().startswith(('=','+','-','@')) else value
        writer.writerow([safe(c[k]) for k in ('registration','aircraft_model','card_code','title','planned_date',
                         'planned_time','workshop','status_name','actual_received_at','actual_completed_at',
                         'assignee_name','assigned_at','latest_note','updated_by_name','updated_at')])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue().encode('utf-8-sig')]),media_type='text/csv; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename="bakim_kartlari.csv"'})


def init_admin(username=None,password=None,full_name=None):
    init_db()
    with conn() as db:
        n = db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
    if n:
        print('Yönetici hesabı zaten mevcut.');return
    if username is None:
        username = input('Yönetici kullanıcı adı: ').strip()
        full_name = input('Ad soyad: ').strip()
        from getpass import getpass
        password = getpass('Güçlü şifre (en az 10 karakter): ')
    valid_password(password)
    username,full_name=clean(username,50),clean(full_name,100)
    with conn() as db:
        db.execute("INSERT INTO users(username,full_name,password_hash,role,active,created_at) VALUES(?,?,?,'admin',1,?)",
                   (username,full_name,hash_password(password),now()))
    print('Yönetici oluşturuldu.')


def demo_seed():
    if DATABASE_URL or os.getenv('VERCEL'):
        raise RuntimeError('Demo data and demo credentials are forbidden in cloud-hosted environments.')
    init_db()
    with conn() as db:
        n = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if n:
            print('Veritabanı dolu; mevcut veriler korunuyor. Demo eklenmedi.');return
        db.execute("INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,? ,?,'admin',?)",
                   ('admin','Demo Yönetici',hash_password('DemoAdmin123!'),now()))
        db.execute("INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,? ,?,'technician',?)",
                   ('teknisyen','Demo Teknisyen',hash_password('DemoTek123!'),now()))
        db.execute("INSERT INTO aircraft(registration,aircraft_model,created_at) VALUES('DEMO-001','A320 (örnek)',?)",(now(),))
        db.execute("INSERT INTO aircraft(registration,aircraft_model,created_at) VALUES('DEMO-002','B737 (örnek)',?)",(now(),))
        sample = [
            (1,'NDT-UT-101','Ultrasonik kontrol talep kartı',-1,'ISL1','planned',None,''),
            (1,'NDT-EC-102','Eddy Current inceleme kartı',0,'ISL2','received',now()[:16],'Kart atölyeye ulaştı; ekipman bekleniyor.'),
            (2,'NDT-PT-103','Penetrant kontrol kartı',1,'IST','in_progress',now()[:16],'Kontrol hazırlıkları başladı.'),
            (2,'NDT-MT-104','Manyetik parçacık kontrol kartı',3,'SAW','on_hold',now()[:16],'Gerekli doküman teyidi bekleniyor.'),
            (1,'NDT-UT-105','İkinci UT muayene kartı',5,'ISL1','planned',None,''),
        ]
        for aircraft_id,code,title,shift,workshop,status,arrived,note in sample:
            cursor=db.execute('''INSERT INTO cards(aircraft_id,card_code,title,planned_date,planned_time,workshop,status,
                actual_received_at,latest_note,updated_at,updated_by,created_at,created_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (aircraft_id,code,title,(datetime.now(ZONE).date()+timedelta(days=shift)).isoformat(),
                 '09:00',workshop,status,arrived,note,now(),1,now(),1))
            db.execute('''INSERT INTO card_events(card_id,user_id,event_type,old_status,new_status,note,
                          recorded_received_at,occurred_at) VALUES(?,1,'Demo kaydı',NULL,?,?,?,?)''',
                       (cursor.lastrowid,status,note or 'Örnek bakım kartı oluşturuldu.',arrived,now()))
    print('ÖRNEK veriler oluşturuldu (gerçek uçak/kart bilgisi değildir).')
    print('Yönetici: admin / DemoAdmin123!')
    print('Teknisyen: teknisyen / DemoTek123!')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Bakım Kartı Takip')
    parser.add_argument('command',nargs='?',choices=['serve','init-admin','demo'],default='serve')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if args.command=='init-admin':
        init_admin()
    elif args.command=='demo':
        demo_seed()
    else:
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
