import os
import re
import secrets
import json
from datetime import datetime, date
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, request,
                   flash, session, jsonify, abort, send_from_directory,
                   send_file, make_response)
from collections import defaultdict
import time as _time

# Einfacher In-Memory Rate-Limiter
_rl_store: dict = defaultdict(list)
def _gq(model):
    """Gibt eine Query für die aktive Gruppe zurück.
    Wenn kein Gruppen-Kontext aktiv ist, werden alle Datensätze zurückgegeben.
    """
    from flask import g as _g
    grp = getattr(_g, 'group', None)
    q = model.query
    if grp and hasattr(model, 'group_id'):
        q = q.filter(model.group_id == grp.id)
    return q


def _rate_limit(key: str, max_calls: int = 5, window: int = 60) -> bool:
    now = _time.time()
    calls = [t for t in _rl_store[key] if now - t < window]
    _rl_store[key] = calls
    if len(calls) >= max_calls:
        return True
    _rl_store[key].append(now)
    return False
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.utils import secure_filename
import requests as http_requests

from config import Config
from models import (db, Group, User, InviteToken, Tour, TourParticipant, TourPhoto, TourVideo,
                    GastroPhoto, TimeVote, LiveLocation,
                    PasswordReset, GastroSpot, GastroReview, POI, TourComment, SiteConfig,
                    RouteRating)

# ─── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config.from_object(Config)
app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)

db.init_app(app)

# ── Auto-migrate flag (actual hook registered after migrate_db is defined) ────
_db_migrated = False

# ── German weekday filter ────────────────────────────────────────────────────
_DE_WEEKDAYS = ['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag']
_DE_MONTHS   = ['','Januar','Februar','März','April','Mai','Juni',
                 'Juli','August','September','Oktober','November','Dezember']

@app.template_global()
def osm_tile_url(lat, lng, zoom=13):
    """Berechnet die OSM-Kachel-URL für einen Koordinatenpunkt."""
    import math
    lat_r = math.radians(float(lat))
    n = 2 ** zoom
    x = int((float(lng) + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return f'https://tile.openstreetmap.org/{zoom}/{x}/{y}.png'

@app.template_filter('de_date')
def de_date_filter(d, fmt='%A, %d.%m.%Y'):
    """Format a date with German weekday names."""
    if d is None:
        return ''
    try:
        weekday = _DE_WEEKDAYS[d.weekday()]
        result  = fmt
        result  = result.replace('%A', weekday)
        result  = result.replace('%a', weekday[:2])
        result  = result.replace('%B', _DE_MONTHS[d.month])
        result  = result.replace('%d', f'{d.day:02d}')
        result  = result.replace('%m', f'{d.month:02d}')
        result  = result.replace('%Y', str(d.year))
        result  = result.replace('%y', str(d.year)[-2:])
        return result
    except Exception:
        return d.strftime(fmt)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Bitte zuerst einloggen.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── Helpers ──────────────────────────────────────────────────────────────────
def allowed_file(filename, allowed):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def organizer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_organizer:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def cfg(key):
    """Read SiteConfig; fall back to DEFAULTS or .env. Never raises."""
    try:
        from sqlalchemy.exc import OperationalError, ProgrammingError
        val = SiteConfig.get(key)
        if val is not None:
            return val
    except (Exception,):
        # Table doesn't exist yet (first run before init-db)
        pass
    env_map = {
        'telegram_bot_token': 'TELEGRAM_BOT_TOKEN',
        'telegram_chat_id':   'TELEGRAM_CHAT_ID',
        'base_url':           'BASE_URL',
    }
    if key in env_map:
        env_val = os.getenv(env_map[key], '')
        if env_val:
            return env_val
    return SiteConfig.DEFAULTS.get(key, '')


def send_mail(to: str, subject: str, body: str) -> bool:
    """E-Mail versenden via SMTP aus .env. Gibt True bei Erfolg zurück."""
    mail_server = os.getenv('MAIL_SERVER', '')
    if not mail_server:
        app.logger.info(f'MAIL_SERVER not set – skipping mail to {to}')
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From']    = os.getenv('MAIL_FROM', 'noreply@dejungenolen.de')
        msg['To']      = to
        port = int(os.getenv('MAIL_PORT', '587'))
        if port == 465:
            s = smtplib.SMTP_SSL(mail_server, port)
        else:
            s = smtplib.SMTP(mail_server, port)
            s.starttls()
        s.login(os.getenv('MAIL_USERNAME', ''), os.getenv('MAIL_PASSWORD', ''))
        s.send_message(msg)
        s.quit()
        app.logger.info(f'Mail sent to {to}: {subject}')
        return True
    except Exception as e:
        app.logger.warning(f'Mail send failed: {e}')
        return False



def send_telegram(text):
    """Send a message to the configured Telegram group/channel."""
    token   = cfg('telegram_bot_token')
    chat_id = cfg('telegram_chat_id')
    if not token or not chat_id:
        return False
    try:
        r = http_requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=5
        )
        return r.status_code == 200
    except Exception as e:
        app.logger.error(f'Telegram error: {e}')
        return False


def extract_gps_from_exif(filepath):
    """Return (lat, lng) or (None, None).
    Uses pure Python first (no deps), then piexif, then Pillow as fallbacks.
    """
    # ── Method 1: Pure Python (no dependencies, always works) ────────────────
    try:
        from exif_gps import read_gps_from_jpeg
        lat, lng = read_gps_from_jpeg(filepath)
        if lat is not None and lng is not None and not (lat == 0 and lng == 0):
            return lat, lng
    except Exception as e:
        app.logger.debug(f'exif_gps fallback: {e}')

    # ── Method 1b: HEIC – scan for embedded EXIF ─────────────────────────────
    try:
        import struct as _struct
        with open(filepath, 'rb') as fh:
            hdr = fh.read(12)
        if len(hdr) >= 8 and hdr[4:8] in (b'ftyp', b'mif1', b'msf1'):
            with open(filepath, 'rb') as fh:
                data = fh.read()
            # Find Exif block embedded in HEIC container
            idx = 0
            while True:
                idx = data.find(b'Exif', idx)
                if idx < 0:
                    break
                chunk = data[idx+6:]
                bo = _struct.unpack_from('>H', chunk, 0)[0] if len(chunk) >= 2 else 0
                if bo in (0x4949, 0x4D4D):  # valid TIFF byte order
                    from exif_gps import read_gps_from_jpeg as _rgj
                    # Write to temp file and try
                    import tempfile, os as _os
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        tmp.write(b'\xff\xd8\xff\xe1')
                        sz = len(chunk) + 6 + 2
                        tmp.write(_struct.pack('>H', min(sz, 65535)))
                        tmp.write(b'Exif\x00\x00')
                        tmp.write(chunk[:60000])
                        tmpname = tmp.name
                    try:
                        lat2, lng2 = _rgj(tmpname)
                        if lat2 is not None and lng2 is not None and not (lat2 == 0 and lng2 == 0):
                            return lat2, lng2
                    except Exception:
                        pass
                    finally:
                        _os.unlink(tmpname)
                idx += 4
    except Exception as e:
        app.logger.debug(f'HEIC GPS scan error: {e}')

    # ── Method 2: piexif ──────────────────────────────────────────────────────
    try:
        import piexif
        exif = piexif.load(filepath)
        gps  = exif.get('GPS', {})
        if piexif.GPSIFD.GPSLatitude in gps:
            def rat(v): return v[0]/v[1] if isinstance(v,tuple) and v[1] else float(v)
            def dms(seq, ref):
                dec = rat(seq[0]) + rat(seq[1])/60 + rat(seq[2])/3600
                r = ref.decode() if isinstance(ref,bytes) else ref
                if r.strip().upper() in ('S','W'): dec = -dec
                return round(dec, 6)
            lat = dms(gps[piexif.GPSIFD.GPSLatitude],  gps.get(piexif.GPSIFD.GPSLatitudeRef,  b'N'))
            lng = dms(gps[piexif.GPSIFD.GPSLongitude], gps.get(piexif.GPSIFD.GPSLongitudeRef, b'E'))
            if -90<=lat<=90 and -180<=lng<=180 and not (lat == 0 and lng == 0):
                return lat, lng
    except ImportError:
        pass
    except Exception as e:
        app.logger.debug(f'piexif GPS error: {e}')

    # ── Method 3: Pillow ──────────────────────────────────────────────────────
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        def _f(v):
            if isinstance(v, tuple) and len(v)==2: return v[0]/v[1] if v[1] else 0.0
            if hasattr(v,'numerator'): return float(v.numerator)/float(v.denominator) if v.denominator else 0.0
            return float(v)
        def _dms(dms, ref):
            dec = _f(dms[0]) + _f(dms[1])/60 + _f(dms[2])/3600
            r = ref.decode() if isinstance(ref,bytes) else str(ref)
            if r.strip().upper() in ('S','W'): dec = -dec
            return round(dec, 6)

        img = Image.open(filepath)
        gps_info = {}
        try:
            exif_obj = img.getexif()
            gps_tag  = next((k for k,v in TAGS.items() if v=='GPSInfo'), None)
            if gps_tag and gps_tag in exif_obj:
                gps_info = {GPSTAGS.get(k,k):v for k,v in exif_obj.get_ifd(gps_tag).items()}
        except Exception:
            pass
        if not gps_info:
            try:
                leg = img._getexif() or {}
                for tid,val in leg.items():
                    if TAGS.get(tid)=='GPSInfo':
                        gps_info = {GPSTAGS.get(k,k):v for k,v in val.items()}
            except Exception:
                pass
        if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
            lat = _dms(gps_info['GPSLatitude'],  gps_info.get('GPSLatitudeRef','N'))
            lng = _dms(gps_info['GPSLongitude'], gps_info.get('GPSLongitudeRef','E'))
            if -90<=lat<=90 and -180<=lng<=180 and not (lat == 0 and lng == 0):
                return lat, lng
    except Exception as e:
        app.logger.debug(f'Pillow GPS error: {e}')

    return None, None


def extract_datetime_from_exif(filepath):
    """Return datetime from EXIF DateTimeOriginal, or None."""
    # Try reading directly from JPEG binary (no deps needed)
    try:
        from exif_gps import read_gps_from_jpeg  # reuse module infrastructure
    except Exception:
        pass

    # Pure stdlib approach: read EXIF tags 36867 (DateTimeOriginal) or 306 (DateTime)
    try:
        with open(filepath, 'rb') as f:
            data = f.read(65536)  # first 64KB is enough for EXIF

        # Find APP1 / EXIF header
        i = 0
        exif_data = None
        while i < len(data) - 4:
            if data[i] == 0xFF and data[i+1] == 0xE1:
                length = (data[i+2] << 8) | data[i+3]
                seg = data[i+4:i+2+length]
                if seg[:4] == b'Exif':
                    exif_data = seg[6:]
                    break
            i += 1
        if not exif_data:
            return None

        import struct
        bom = exif_data[:2]
        if bom == b'II': big_endian = False
        elif bom == b'MM': big_endian = True
        else: return None
        endian = '>' if big_endian else '<'

        ifd0 = struct.unpack_from(f'{endian}I', exif_data, 4)[0]
        num  = struct.unpack_from(f'{endian}H', exif_data, ifd0)[0]

        date_str = None
        for n in range(num):
            off   = ifd0 + 2 + n * 12
            tag   = struct.unpack_from(f'{endian}H', exif_data, off)[0]
            if tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
                voff = struct.unpack_from(f'{endian}I', exif_data, off+8)[0]
                end  = exif_data.find(b'\x00', voff)
                date_str = exif_data[voff:end].decode('ascii', errors='ignore')
                if tag == 36867:  # prefer DateTimeOriginal, stop searching
                    break

        if date_str:
            # Format: "YYYY:MM:DD HH:MM:SS"
            return datetime.strptime(date_str.strip(), '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    return None


    """Return dict with track points, km, ascent; or None on error."""
    try:
        import gpxpy
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            gpx = gpxpy.parse(f)

        points = []
        for track in gpx.tracks:
            for seg in track.segments:
                for pt in seg.points:
                    points.append({
                        'lat': round(pt.latitude, 6),
                        'lng': round(pt.longitude, 6),
                        'ele': round(pt.elevation or 0, 1)
                    })

        km     = round((gpx.length_3d() or gpx.length_2d() or 0) / 1000, 1)
        ascent = round(gpx.get_uphill_downhill().uphill or 0, 0)

        return {'points': points, 'km': km, 'ascent': int(ascent)}
    except Exception as e:
        app.logger.error(f'GPX parse error: {e}')
        return None


# ─── Context processor ────────────────────────────────────────────────────────
@app.context_processor
def inject_group_context():
    from flask import g as _g
    return {'current_group': getattr(_g, 'group', None),
            'all_groups': Group.query.filter_by(is_active=True).all()
                          if (current_user.is_authenticated and current_user.role=='admin') else []}


@app.context_processor
def inject_globals():
    upcoming  = []
    tg_user   = ''
    tg_invite = ''
    tg_user   = ''
    tg_invite = ''
    tg_link   = ''
    if current_user.is_authenticated:
        today = date.today()
        upcoming = _gq(Tour).filter(
            Tour.tour_date >= today,
            Tour.tour_date != date(9999, 12, 31),
            Tour.status == 'planned'
        ).order_by(Tour.tour_date).limit(3).all()
        try:
            tg_user   = (cfg('telegram_chat_username') or '').lstrip('@')
            tg_invite = (cfg('telegram_invite_link') or '').strip()
            tg_link = tg_invite if tg_invite else (f'https://t.me/{tg_user}' if tg_user else '')
        except Exception:
            pass
    return dict(upcoming_tours=upcoming, today_date=date.today(),
                telegram_username=tg_user,
                telegram_invite_link=tg_invite,
                telegram_link=tg_link)

# Make Python's enumerate available in templates
app.jinja_env.globals['enumerate'] = enumerate
app.jinja_env.globals['hasattr']   = hasattr


# ─── Auth routes ──────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        # Rate limiting: max 10 Login-Versuche pro IP pro Minute
        ip = request.remote_addr or 'unknown'
        if _rate_limit(f'login:{ip}', max_calls=10, window=60):
            flash('Zu viele Versuche. Bitte eine Minute warten.', 'danger')
            return render_template('auth/login.html')
        user  = User.query.filter_by(email=email).first()
        if user and user.check_password(pw):
            if not user.is_active:
                flash('Dein Konto ist gesperrt. Wende dich an einen Admin.', 'danger')
                return redirect(url_for('login'))
            login_user(user, remember=request.form.get('remember'))
            try:
                from datetime import datetime as _dt
                user.last_login = _dt.utcnow()
                db.session.commit()
            except Exception:
                pass
            return redirect(request.args.get('next') or url_for('index'))
        flash('E-Mail oder Passwort falsch.', 'danger')
    return render_template('auth/login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Erfolgreich abgemeldet.', 'success')
    return redirect(url_for('login'))


@app.route('/registrieren/<token>', methods=['GET', 'POST'])
def register(token):
    invite = InviteToken.query.filter_by(token=token, used=False).first_or_404()
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        name     = request.form.get('name', '').strip()
        nickname = request.form.get('nickname', '').strip()
        pw       = request.form.get('password', '')
        pw2      = request.form.get('password2', '')
        bicycle  = request.form.get('bicycle_type', 'trekking')
        ebike    = bool(request.form.get('is_ebike'))

        if pw != pw2:
            flash('Passwörter stimmen nicht überein.', 'danger')
            return render_template('auth/register.html', invite=invite)
        if len(pw) < 6:
            flash('Passwort muss mindestens 6 Zeichen haben.', 'danger')
            return render_template('auth/register.html', invite=invite)
        if User.query.filter_by(email=email).first():
            flash('Diese E-Mail ist bereits registriert.', 'danger')
            return render_template('auth/register.html', invite=invite)

        user = User(email=email, name=name, nickname=nickname,
                    bicycle_type=bicycle, is_ebike=ebike)
        user.set_password(pw)
        # First user gets admin role
        if User.query.count() == 0:
            user.role = 'admin'

        db.session.add(user)
        invite.used = True
        db.session.commit()

        login_user(user)
        _group_name = invite.group.name if invite.group else 'De jungen Olen'
        flash(f'Willkommen bei {_group_name}, {user.display_name}! 🚴', 'success')
        return redirect(url_for('index'))

    return render_template('auth/register.html', invite=invite)


@app.route('/passwort-vergessen', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        ip = request.remote_addr or 'unknown'
        if _rate_limit(f'reset:{ip}', max_calls=5, window=300):
            flash('Zu viele Anfragen. Bitte 5 Minuten warten.', 'danger')
            return render_template('auth/forgot_password.html')
        user  = User.query.filter_by(email=email).first()
        RESET_MSG = ('Falls diese E-Mail-Adresse registriert ist, wurde ein Reset-Link gesendet. '
                      'Bitte auch den Spam-Ordner prüfen. Der Link ist 1 Stunde gültig.')
        if user:
            token = secrets.token_urlsafe(32)
            pr    = PasswordReset(user_id=user.id, token=token)
            db.session.add(pr)
            db.session.commit()
            reset_url = url_for('reset_password', token=token, _external=True)
            sent = send_mail(
                to=user.email,
                subject='De jungen Olen – Passwort zurücksetzen',
                body=(f'Hallo {user.name},\n\n'
                      f'du hast einen Passwort-Reset angefordert.\n\n'
                      f'Link (gültig 1 Stunde):\n{reset_url}\n\n'
                      f'Falls du das nicht warst, ignoriere diese E-Mail.')
            )
            if app.debug and not sent:
                flash(f'[Dev] Reset-Link: {reset_url}', 'info')
            else:
                flash(RESET_MSG, 'info')
        else:
            flash(RESET_MSG, 'info')
    return render_template('auth/forgot_password.html')


@app.route('/passwort-reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    pr = PasswordReset.query.filter_by(token=token, used=False).first_or_404()
    if request.method == 'POST':
        pw  = request.form.get('password', '')
        pw2 = request.form.get('password2', '')
        if pw != pw2 or len(pw) < 6:
            flash('Passwörter stimmen nicht überein oder mindestens 6 Zeichen nötig.', 'danger')
            return render_template('auth/reset_password.html')
        pr.user.set_password(pw)
        pr.used = True
        db.session.commit()
        flash('Passwort geändert. Bitte einloggen.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/reset_password.html')


# ─── Main / Dashboard ─────────────────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    today  = date.today()
    upcoming = _gq(Tour).filter(
        Tour.tour_date >= today,
        Tour.tour_date != date(9999, 12, 31),
        Tour.status == 'planned'
    ).order_by(Tour.tour_date).all()
    from sqlalchemy.orm import selectinload
    recent = (_gq(Tour)
              .filter(Tour.status == 'completed',
                      Tour.tour_date != date(9999, 12, 31))
              .order_by(Tour.tour_date.desc())
              .limit(5).all())

    # Top proposals for dashboard (max 3, sorted by score)
    geplante = (_gq(Tour)
                .filter(Tour.status == 'planned', Tour.tour_date == date(9999, 12, 31))
                .order_by(Tour.created_at.desc())
                .limit(3).all())

    # Cover-Fotos für Hero-Karte (erstes Foto je Tour)
    tour_ids = [t.id for t in upcoming] + [t.id for t in recent]
    cover_photos = {}
    if tour_ids:
        first_photos = (TourPhoto.query
                        .filter(TourPhoto.tour_id.in_(tour_ids))
                        .order_by(TourPhoto.tour_id, TourPhoto.sort_order.asc().nullslast(),
                                  TourPhoto.taken_at.asc().nullslast())
                        .all())
        seen = set()
        for p in first_photos:
            if p.tour_id not in seen:
                cover_photos[p.tour_id] = p
                seen.add(p.tour_id)

    return render_template('index.html', upcoming=upcoming, recent=recent,
                           today=today,
                           geplante_touren=geplante,
                           cover_photos=cover_photos,
                           birthdays=upcoming_birthdays(),
                           memories=tours_this_day_past_years(),
                           milestones=group_milestones())


# ─── Tour routes ──────────────────────────────────────────────────────────────
@app.route('/api/gpx/<int:tour_id>')
@login_required
def api_gpx_preview(tour_id):
    """Vereinfachte GPX-Punkte für Kartenvorschau."""
    tour = Tour.query.get_or_404(tour_id)
    if not tour.gpx_file:
        return jsonify({'points': [], 'meeting': None})
    path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
    if not os.path.exists(path):
        return jsonify({'points': [], 'meeting': None})
    data = parse_gpx(path)
    if not data or not data.get('points'):
        return jsonify({'points': [], 'meeting': None})
    # Vereinfachen: max 80 Punkte
    pts   = data['points']
    step  = max(1, len(pts) // 80)
    simplified = [[p['lat'], p['lng']] for p in pts[::step]]
    if pts[-1] not in (pts[::step]):
        simplified.append([pts[-1]['lat'], pts[-1]['lng']])
    meeting = None
    if tour.meeting_lat and tour.meeting_lng:
        meeting = [tour.meeting_lat, tour.meeting_lng]
    return jsonify({'points': simplified, 'meeting': meeting})


@app.route('/api/exif-debug', methods=['POST'])
@login_required
def api_exif_debug():
    """Diagnose-Endpunkt: zeigt was beim EXIF-Parsing eines Fotos gefunden wird."""
    f = request.files.get('photo')
    if not f:
        return jsonify({'error': 'kein Foto übergeben'}), 400

    data = f.read()
    result = {
        'filename': f.filename,
        'size_bytes': len(data),
        'first_bytes_hex': data[:16].hex(),
        'is_jpeg': data[:2] == b'\xff\xd8',
        'is_heic': len(data) >= 12 and data[4:8] in (b'ftyp', b'mif1', b'msf1'),
        'is_png': data[:8] == b'\x89PNG\r\n\x1a\n',
    }

    segments_found = []
    if result['is_jpeg']:
        i = 2
        while i < len(data) - 4:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i+1]
            if marker in (0xD8, 0xD9, 0xDA):
                if marker == 0xDA:
                    break
                i += 2
                continue
            try:
                seg_len = int.from_bytes(data[i+2:i+4], 'big')
            except Exception:
                break
            if marker == 0xE1:
                hdr = data[i+4:i+10]
                seg_info = {'marker': hex(marker), 'length': seg_len, 'header': hdr.hex()}
                if hdr[:4] == b'Exif':
                    exif_block = data[i+10:i+2+seg_len]
                    bom = exif_block[:2]
                    seg_info['byte_order'] = bom.decode('ascii', errors='replace')
                    seg_info['exif_block_len'] = len(exif_block)
                    try:
                        import struct
                        big_endian = bom == b'MM'
                        endian = '>' if big_endian else '<'
                        ifd0_off = struct.unpack_from(f'{endian}I', exif_block, 4)[0]
                        n = struct.unpack_from(f'{endian}H', exif_block, ifd0_off)[0]
                        tags = []
                        gps_ifd = None
                        for k in range(n):
                            eo = ifd0_off + 2 + k*12
                            tag = struct.unpack_from(f'{endian}H', exif_block, eo)[0]
                            tags.append(hex(tag))
                            if tag == 0x8825:
                                gps_ifd = struct.unpack_from(f'{endian}I', exif_block, eo+8)[0]
                        seg_info['ifd0_tag_count'] = n
                        seg_info['ifd0_tags'] = tags
                        seg_info['gps_ifd_pointer'] = gps_ifd
                        if gps_ifd:
                            ng = struct.unpack_from(f'{endian}H', exif_block, gps_ifd)[0]
                            gps_tags = []
                            for k in range(ng):
                                eo = gps_ifd + 2 + k*12
                                tag = struct.unpack_from(f'{endian}H', exif_block, eo)[0]
                                ttype = struct.unpack_from(f'{endian}H', exif_block, eo+2)[0]
                                cnt = struct.unpack_from(f'{endian}I', exif_block, eo+4)[0]
                                gps_tags.append({'tag': hex(tag), 'type': ttype, 'count': cnt})
                            seg_info['gps_ifd_tag_count'] = ng
                            seg_info['gps_ifd_tags'] = gps_tags
                    except Exception as ex:
                        seg_info['parse_error'] = str(ex)
                segments_found.append(seg_info)
            i += 2 + seg_len

    result['app1_segments'] = segments_found

    import tempfile, os as _os
    suffix = '.heic' if result['is_heic'] else '.jpg'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmpname = tmp.name

    try:
        lat, lng = extract_gps_from_exif(tmpname)
        result['extract_gps_from_exif_result'] = {'lat': lat, 'lng': lng}
    except Exception as ex:
        result['extract_gps_from_exif_result'] = {'error': str(ex)}

    # ── Verbose trace: jede Methode einzeln mit Fehlerdetails ─────────────────
    methods = {}

    # Method 1: exif_gps.py (pure python)
    try:
        import exif_gps as _eg
        import importlib
        importlib.reload(_eg)
        lat1, lng1 = _eg.read_gps_from_jpeg(tmpname)
        methods['method1_exif_gps_py'] = {'lat': lat1, 'lng': lng1}
    except Exception as ex:
        import traceback
        methods['method1_exif_gps_py'] = {'error': str(ex), 'trace': traceback.format_exc()[-500:]}

    # Method 1 verbose: replicate internal steps with tag-level detail
    try:
        import struct as _s
        with open(tmpname, 'rb') as fh:
            raw = fh.read()
        i = 0
        candidates = []
        while i < len(raw) - 4:
            if raw[i] == 0xFF and raw[i+1] == 0xE1:
                length = _s.unpack('>H', raw[i+2:i+4])[0]
                seg = raw[i+4:i+2+length]
                if seg[:6] in (b'Exif\x00\x00', b'Exif\x00\xff'):
                    candidates.append(seg[6:])
                i += 2 + length
            else:
                i += 1
        trace = {'candidate_count': len(candidates)}
        if candidates:
            ed = candidates[0]
            bom = ed[:2]
            big = (bom == b'MM')
            endian = '>' if big else '<'
            trace['byte_order'] = bom.decode('ascii', errors='replace')
            ifd0_off = _s.unpack_from(f'{endian}I', ed, 4)[0]
            n = _s.unpack_from(f'{endian}H', ed, ifd0_off)[0]
            gps_off = None
            for k in range(n):
                eo = ifd0_off + 2 + k*12
                tag = _s.unpack_from(f'{endian}H', ed, eo)[0]
                if tag == 0x8825:
                    gps_off = _s.unpack_from(f'{endian}I', ed, eo+8)[0]
            trace['gps_ifd_offset'] = gps_off
            if gps_off:
                ng = _s.unpack_from(f'{endian}H', ed, gps_off)[0]
                gps_raw = {}
                for k in range(ng):
                    eo = gps_off + 2 + k*12
                    tag = _s.unpack_from(f'{endian}H', ed, eo)[0]
                    ttype = _s.unpack_from(f'{endian}H', ed, eo+2)[0]
                    cnt = _s.unpack_from(f'{endian}I', ed, eo+4)[0]
                    voff = _s.unpack_from(f'{endian}I', ed, eo+8)[0]
                    entry = {'type': ttype, 'count': cnt, 'value_offset_raw': voff}
                    # Try to decode the actual value like _read_tag_value does
                    try:
                        if ttype == 5:  # RATIONAL
                            total = 8 * cnt
                            off = voff if total > 4 else None
                            if off is not None:
                                vals = []
                                for vi in range(cnt):
                                    num, den = _s.unpack_from(f'{endian}II', ed, off + vi*8)
                                    vals.append(num/den if den else None)
                                entry['decoded'] = vals
                            else:
                                entry['decoded'] = 'INLINE (unexpected for RATIONAL)'
                        elif ttype == 2:  # ASCII
                            total = cnt
                            if total <= 4:
                                inline_bytes = _s.pack(f'{endian}I', voff)
                                entry['decoded'] = inline_bytes.split(b'\x00')[0].decode('ascii', errors='replace')
                                entry['decoded_method'] = 'inline'
                            else:
                                end = ed.find(b'\x00', voff)
                                entry['decoded'] = ed[voff:end].decode('ascii', errors='replace')
                                entry['decoded_method'] = 'external_offset'
                    except Exception as tagex:
                        entry['decode_error'] = str(tagex)
                    gps_raw[hex(tag)] = entry
                trace['gps_tags_decoded'] = gps_raw
        methods['method1_verbose_trace'] = trace
    except Exception as ex:
        import traceback
        methods['method1_verbose_trace'] = {'error': str(ex), 'trace': traceback.format_exc()[-800:]}

    # Method 2: piexif
    try:
        import piexif
        exif_dict = piexif.load(tmpname)
        gps_piexif = exif_dict.get('GPS', {})
        methods['method2_piexif'] = {
            'available': True,
            'gps_keys': [hex(k) for k in gps_piexif.keys()],
            'raw_gps': {hex(k): str(v)[:100] for k, v in gps_piexif.items()},
        }
    except ImportError:
        methods['method2_piexif'] = {'available': False, 'reason': 'piexif not installed'}
    except Exception as ex:
        methods['method2_piexif'] = {'error': str(ex)}

    # Method 3: Pillow
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        img = Image.open(tmpname)
        exif_obj = img.getexif()
        gps_tag = next((k for k, v in TAGS.items() if v == 'GPSInfo'), None)
        if gps_tag and gps_tag in exif_obj:
            gps_info = {GPSTAGS.get(k, k): v for k, v in exif_obj.get_ifd(gps_tag).items()}
            methods['method3_pillow'] = {
                'available': True,
                'gps_info': {k: str(v)[:100] for k, v in gps_info.items()},
            }
        else:
            methods['method3_pillow'] = {'available': True, 'gps_info': None, 'note': 'kein GPSInfo IFD gefunden'}
    except ImportError:
        methods['method3_pillow'] = {'available': False, 'reason': 'Pillow not installed'}
    except Exception as ex:
        methods['method3_pillow'] = {'error': str(ex)}

    result['methods_detail'] = methods
    _os.unlink(tmpname)

    return jsonify(result)


@app.route('/touren')
@login_required
def tour_list():
    today = date.today()
    # Touren mit Datum (zukünftig)
    tours_dated = _gq(Tour).filter(
        Tour.tour_date >= today,
        Tour.tour_date != date(9999, 12, 31),
        Tour.status == 'planned'
    ).order_by(Tour.tour_date).all()

    # Touren ohne Termin
    tours_open = _gq(Tour).filter(
        Tour.tour_date == date(9999, 12, 31),
        Tour.status == 'planned'
    ).order_by(Tour.created_at.desc()).all()

    all_tours = tours_dated + tours_open

    default_lat = cfg('default_meeting_lat') or '52.942'
    default_lng = cfg('default_meeting_lng') or '9.097'

    # Cover-Fotos
    tour_ids = [t.id for t in all_tours]
    cover_photos = {}
    if tour_ids:
        first_photos = (TourPhoto.query
                        .filter(TourPhoto.tour_id.in_(tour_ids))
                        .order_by(TourPhoto.tour_id,
                                  TourPhoto.sort_order.asc().nullslast(),
                                  TourPhoto.taken_at.asc().nullslast())
                        .all())
        seen = set()
        for p in first_photos:
            if p.tour_id not in seen:
                cover_photos[p.tour_id] = p
                seen.add(p.tour_id)

    # Bewertungen für offene Touren (batch)
    open_ids = [t.id for t in tours_open]
    rating_map = {}
    if open_ids:
        from collections import defaultdict
        all_ratings = RouteRating.query.filter(RouteRating.tour_id.in_(open_ids)).all()
        ratings_by_tour = defaultdict(list)
        for r in all_ratings:
            ratings_by_tour[r.tour_id].append(r)
        for t in tours_open:
            ratings = ratings_by_tour[t.id]
            rating_map[t.id] = {
                'good':  sum(1 for r in ratings if r.rating == 'good'),
                'ok':    sum(1 for r in ratings if r.rating == 'ok'),
                'bad':   sum(1 for r in ratings if r.rating == 'bad'),
                'mine':  next((r for r in ratings if r.user_id == current_user.id), None),
                'total': len(ratings),
            }

    return render_template('touren/list.html',
                           tours=tours_dated, tours_open=tours_open,
                           today=today, weather_map={},
                           default_lat=default_lat, default_lng=default_lng,
                           cover_photos=cover_photos, rating_map=rating_map)


@app.route('/touren/neu', methods=['GET', 'POST'])
@login_required
@organizer_required
def tour_create():
    if request.method == 'POST':
        title      = request.form.get('title', '').strip()
        desc       = request.form.get('description', '').strip()
        tour_date  = request.form.get('tour_date', '').strip()
        start_time = request.form.get('start_time', '')
        difficulty = request.form.get('difficulty', 'mittel')
        meet_lat   = request.form.get('meeting_lat', '')
        meet_lng   = request.form.get('meeting_lng', '')
        meet_desc  = request.form.get('meeting_desc', '').strip()

        if not title:
            flash('Bitte einen Titel eingeben.', 'danger')
            return render_template('touren/create.html',
                                   difficulties=Config.DIFFICULTY_CHOICES)

        approx_km     = request.form.get('approx_km', '').strip()
        external_link = request.form.get('external_link', '').strip()

        tour = Tour(
            title         = title,
            description   = desc,
            tour_date     = datetime.strptime(tour_date, '%Y-%m-%d').date() if tour_date else date(9999, 12, 31),
            start_time    = start_time or None,
            difficulty    = difficulty,
            approx_km     = float(approx_km) if approx_km else None,
            external_link = external_link or None,
            meeting_lat   = float(meet_lat) if meet_lat else None,
            meeting_lng   = float(meet_lng) if meet_lng else None,
            meeting_desc  = meet_desc or None,
            created_by    = current_user.id
        )
        # Marker for "date open" - we use 9999-12-31 as sentinel value
        # because SQLite cannot ALTER COLUMN to remove NOT NULL constraint
        tour._date_open = not bool(tour_date)
        db.session.add(tour)
        try:
            db.session.flush()  # get ID before commit
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'tour_create flush error: {e}', exc_info=True)
            # Spalten fehlen evtl. noch – ohne neue Felder nochmal versuchen
            tour.approx_km     = None
            tour.external_link = None
            db.session.add(tour)
            try:
                db.session.flush()
            except Exception as e2:
                db.session.rollback()
                flash(f'Fehler beim Speichern: {e2}', 'danger')
                return redirect(url_for('tour_create'))

        # Copy GPX from proposal if available
        proposal_gpx = request.form.get('proposal_gpx_file', '').strip()
        new_gpx = request.files.get('gpx_file')

        if new_gpx and new_gpx.filename and allowed_file(new_gpx.filename, {'gpx'}):
            os.makedirs(app.config['UPLOAD_FOLDER_GPX'], exist_ok=True)
            new_fname = f'tour_{tour.id}_{secrets.token_hex(4)}.gpx'
            save_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], new_fname)
            new_gpx.save(save_path)
            tour.gpx_file = new_fname
            parsed = parse_gpx(save_path)
            if parsed:
                tour.gpx_km     = parsed.get('km')
                tour.gpx_ascent = parsed.get('ascent')
        elif proposal_gpx:
            src = os.path.join(app.config['UPLOAD_FOLDER_GPX'], proposal_gpx)
            if os.path.exists(src):
                import shutil
                new_fname = f'tour_{tour.id}_{secrets.token_hex(4)}.gpx'
                dst = os.path.join(app.config['UPLOAD_FOLDER_GPX'], new_fname)
                shutil.copy2(src, dst)
                tour.gpx_file = new_fname
                parsed = parse_gpx(dst)
                if parsed:
                    tour.gpx_km     = parsed.get('km')
                    tour.gpx_ascent = parsed.get('ascent')

        # Auto-RSVP creator
        rsvp = TourParticipant(tour_id=tour.id, user_id=current_user.id, status='attending')
        db.session.add(rsvp)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'tour_create commit error: {e}', exc_info=True)
            flash(f'Datenbankfehler beim Speichern: {e}', 'danger')
            return redirect(url_for('tour_create'))

        # Telegram notification
        try:
            datum = ('Datum noch offen' if tour.is_date_open
                     else tour.tour_date.strftime('%d.%m.%Y'))
            km_str = ''
            if tour.gpx_km:
                km_str = f'📏 {tour.gpx_km} km\n'
            elif tour.approx_km:
                km_str = f'📏 ca. {tour.approx_km:.0f} km\n'
            tg_msg = (
                f'🚴 <b>Neue Tour geplant!</b>\n\n'
                f'📋 <b>{title}</b>\n'
                f'📅 {datum}'
                f'{" um " + start_time + " Uhr" if start_time and not tour.is_date_open else ""}\n'
                f'{km_str}'
                f'💪 Schwierigkeit: {tour.difficulty_label}\n'
            )
            if meet_desc:
                tg_msg += f'📍 Treffpunkt: {meet_desc}\n'
            tg_msg += f'\n👉 {app.config["BASE_URL"]}/touren/{tour.id}'
            send_telegram(tg_msg)
        except Exception as e:
            app.logger.warning(f'Telegram notification failed: {e}')

        flash('Tour erfolgreich erstellt!', 'success')
        return redirect(url_for('tour_detail', tour_id=tour.id))

    # Letzten Treffpunkt aus der neuesten Tour vorbelegen falls kein Admin-Default gesetzt
    last_tour = None
    if not cfg('default_meeting_lat'):
        last_tour = (_gq(Tour)
                     .filter(Tour.created_by == current_user.id,
                             Tour.meeting_lat != None,
                             Tour.tour_date != date(9999, 12, 31))
                     .order_by(Tour.tour_date.desc())
                     .first())

    return render_template('touren/create.html',
                           difficulties=Config.DIFFICULTY_CHOICES,
                           today=date.today(),
                           default_time=cfg('default_start_time') or '09:00',
                           default_meeting_desc=cfg('default_meeting_desc'),
                           default_meeting_lat=cfg('default_meeting_lat') or (last_tour.meeting_lat if last_tour else None),
                           default_meeting_lng=cfg('default_meeting_lng') or (last_tour.meeting_lng if last_tour else None),
                           default_meeting_desc_last=(last_tour.meeting_desc if last_tour and not cfg('default_meeting_desc') else None),
                           prefill=session.pop('prefill_from_proposal', None))


@__import__('functools').lru_cache(maxsize=64)
def parse_gpx(filepath):
    """Return dict with track points, km, ascent; or None on error."""
    try:
        import gpxpy
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            gpx = gpxpy.parse(f)

        points = []
        for track in gpx.tracks:
            for seg in track.segments:
                for pt in seg.points:
                    points.append({
                        'lat': round(pt.latitude, 6),
                        'lng': round(pt.longitude, 6),
                        'ele': round(pt.elevation or 0, 1)
                    })

        km     = round((gpx.length_3d() or gpx.length_2d() or 0) / 1000, 1)
        ascent = round(gpx.get_uphill_downhill().uphill or 0, 0)

        return {'points': points, 'km': km, 'ascent': int(ascent)}
    except Exception as e:
        app.logger.error(f'GPX parse error: {e}')
        return None


@app.route('/touren/<int:tour_id>')
@login_required
def tour_detail(tour_id):
    tour = Tour.query.get_or_404(tour_id)

    # Current user's RSVP
    my_rsvp = TourParticipant.query.filter_by(
        tour_id=tour_id, user_id=current_user.id
    ).first()

    # Participants grouped by status
    attending = TourParticipant.query.filter_by(tour_id=tour_id, status='attending').limit(200).all()
    maybe     = TourParticipant.query.filter_by(tour_id=tour_id, status='maybe').limit(200).all()
    declined  = TourParticipant.query.filter_by(tour_id=tour_id, status='declined').limit(200).all()

    # GPX data for map
    gpx_data = None
    if tour.gpx_file:
        gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
        if os.path.exists(gpx_path):
            gpx_data = parse_gpx(gpx_path)

    # Photos sorted: sort_order zuerst (Drag & Drop), dann EXIF-Datum
    from sqlalchemy import text as sa_text
    photos = tour.photos.order_by(
        sa_text('COALESCE(sort_order, 999999) ASC'),
        TourPhoto.taken_at.asc().nullslast(),
        TourPhoto.created_at.asc()
    ).all()
    comments = (TourComment.query
                .filter_by(tour_id=tour_id, parent_id=None)
                .order_by(TourComment.created_at)
                .all())

    # All active users for organizer add-participant dropdown
    all_users = _gq(User).filter_by(is_active=True).order_by(User.name).all() \
                if current_user.is_organizer or current_user.is_admin else []
    participant_ids = {p.user_id for p in attending + maybe + declined}

    videos = TourVideo.query.filter_by(tour_id=tour_id).order_by(TourVideo.created_at).all()
    return render_template('touren/detail.html',
                           tour=tour,
                           my_rsvp=my_rsvp,
                           attending=attending,
                           maybe=maybe,
                           declined=declined,
                           gpx_data=json.dumps(gpx_data) if gpx_data else 'null',
                           photos=photos,
                           videos=videos,
                           comments=comments,
                           all_users=all_users,
                           participant_ids=participant_ids,
                           today=date.today())


@app.route('/touren/<int:tour_id>/rsvp', methods=['POST'])
@login_required
def tour_rsvp(tour_id):
    tour   = Tour.query.get_or_404(tour_id)
    status = request.form.get('status', 'attending')
    if status not in ('attending', 'maybe', 'declined'):
        abort(400)
    if tour.is_date_open:
        flash('Anmeldung erst möglich wenn ein Termin feststeht.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id))

    rsvp = TourParticipant.query.filter_by(
        tour_id=tour_id, user_id=current_user.id
    ).first()
    if rsvp:
        rsvp.status = status
    else:
        rsvp = TourParticipant(tour_id=tour_id, user_id=current_user.id, status=status)
        db.session.add(rsvp)
    db.session.commit()

    labels = {'attending': 'Dabei!', 'maybe': 'Vielleicht', 'declined': 'Abgesagt'}
    flash(f'Anmeldung: {labels[status]}', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


@app.route('/touren/<int:tour_id>/gpx', methods=['POST'])
@login_required
@organizer_required
def tour_upload_gpx(tour_id):
    tour = Tour.query.get_or_404(tour_id)
    f = request.files.get('gpx_file')
    if not f or not allowed_file(f.filename, app.config['ALLOWED_GPX_EXTENSIONS']):
        flash('Bitte eine gültige GPX-Datei hochladen.', 'danger')
        return redirect(url_for('tour_detail', tour_id=tour_id))

    filename = f'{tour_id}_{secrets.token_hex(6)}.gpx'
    save_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], filename)
    f.save(save_path)

    # Parse to extract stats
    parsed = parse_gpx(save_path)
    tour.gpx_file = filename
    if parsed:
        tour.gpx_km     = parsed['km']
        tour.gpx_ascent = parsed['ascent']
    db.session.commit()

    flash(f'GPX hochgeladen! {parsed["km"]} km, {parsed["ascent"]} m Anstieg' if parsed else 'GPX hochgeladen.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


def _pillow_ok():
    """Prüft ob Pillow inkl. C-Extension funktioniert."""
    try:
        from PIL import Image, _imaging  # noqa: F401
        Image.new('RGB', (1, 1)).tobytes()
        return True
    except Exception:
        return False


def _resize_photo_if_needed(path, max_px=1600, quality=85):
    """Bild verkleinern wenn nötig. Pillow > ImageMagick. Korrigiert EXIF-Rotation."""
    import subprocess

    # ── Method 1: Pillow (bevorzugt: verlustarm, EXIF-aware) ──────────────────
    if _pillow_ok():
        try:
            from PIL import Image as PILImage, ExifTags, ImageOps
            img = PILImage.open(path)

            # EXIF-Rotation korrigieren (transpose respektiert Orientation-Tag)
            img = ImageOps.exif_transpose(img)

            w, h = img.size
            if max(w, h) <= max_px:
                # Trotzdem speichern um EXIF-Rotation zu fixieren
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(path, format='JPEG', quality=quality,
                         optimize=True, progressive=True)
                return False

            ratio = max_px / max(w, h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), PILImage.LANCZOS)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(path, format='JPEG', quality=quality,
                     optimize=True, progressive=True)
            app.logger.info(f'Pillow resized: {w}x{h} → {new_w}x{new_h}')
            return True
        except Exception as e:
            app.logger.warning(f'Pillow resize failed: {e} – versuche ImageMagick')

    # ── Method 2: ImageMagick (Fallback) ──────────────────────────────────────
    try:
        result = subprocess.run(
            ['convert', '-auto-orient', path,
             '-resize', f'{max_px}x{max_px}>',
             '-quality', str(quality),
             '-strip',   # EXIF-Daten nach auto-orient entfernen
             path],
            capture_output=True, timeout=30
        )
        if result.returncode == 0:
            app.logger.info(f'ImageMagick resized: {os.path.basename(path)}')
            return True
        app.logger.warning(f'ImageMagick failed: {result.stderr.decode()[:200]}')
    except FileNotFoundError:
        app.logger.warning('ImageMagick (convert) nicht gefunden')
    except Exception as e:
        app.logger.warning(f'ImageMagick error: {e}')

    return False


@app.route('/fotos/<int:photo_id>/caption', methods=['POST'])
@login_required
def photo_set_caption(photo_id):
    """Foto-Beschriftung setzen."""
    photo = TourPhoto.query.get_or_404(photo_id)
    if not (current_user.is_admin or current_user.is_organizer or
            photo.user_id == current_user.id or
            photo.tour.created_by == current_user.id):
        return jsonify({'error': 'forbidden'}), 403
    # force=True: parst JSON unabhängig vom Content-Type Header
    data    = request.get_json(force=True, silent=True) or {}
    caption = (data.get('caption') or request.form.get('caption') or '').strip() or None
    photo.caption = caption
    db.session.commit()
    return jsonify({'ok': True, 'caption': photo.caption})


@app.route('/touren/<int:tour_id>/fotos', methods=['POST'])
@login_required
def tour_upload_photos(tour_id):
    import zipfile as _zipfile
    import io as _io

    # Rate-Limit: max 5 Upload-Requests pro Minute pro User
    if _rate_limit(f'photo_upload:{current_user.id}', max_calls=5, window=60):
        flash('Zu viele Uploads – bitte warte eine Minute.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id) + '#fotos')

    tour   = Tour.query.get_or_404(tour_id)
    files  = request.files.getlist('photos')
    os.makedirs(app.config['UPLOAD_FOLDER_PHOTOS'], exist_ok=True)
    count     = 0
    gps_count = 0
    skipped   = 0
    resized   = 0
    zip_count = 0

    def _check_magic(data: bytes) -> bool:
        h = data[:12]
        if h[:3] == b'\xff\xd8\xff': return True   # JPEG
        if h[:4] == b'\x89PNG':      return True   # PNG
        if h[:4] == b'RIFF' and b'WEBP' in h: return True  # WebP
        if h[4:8] in (b'ftyp', b'mif1', b'msf1', b'heic'): return True  # HEIC
        return False

    def _process_image_bytes(data, original_name, form_idx=None):
        """Save image bytes, run resize + GPS, return TourPhoto or None.
        form_idx: index used by client-side JS for gps_lat_N/gps_lng_N lookup
        (falls back to internal counter if not provided, e.g. for ZIP entries)."""
        nonlocal count, gps_count, resized
        ext = original_name.rsplit('.', 1)[-1].lower()
        if ext not in app.config['ALLOWED_PHOTO_EXTENSIONS']:
            return None
        if not _check_magic(data):
            app.logger.warning(f'Rejected upload with invalid magic bytes: {original_name}')
            return None
        filename  = f'{tour_id}_{secrets.token_hex(8)}.{ext}'
        save_path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], filename)
        with open(save_path, 'wb') as fh:
            fh.write(data)
        size_before = os.path.getsize(save_path)

        # GPS VOR dem Resize auslesen – ImageMagick -strip entfernt EXIF!
        lat, lng = extract_gps_from_exif(save_path)
        taken_at = extract_datetime_from_exif(save_path)

        _resize_photo_if_needed(save_path)
        if os.path.getsize(save_path) < size_before:
            resized += 1

        # Fallback: use client-extracted GPS if server EXIF failed
        # (mobile browsers often strip GPS before upload)
        idx_key = form_idx if form_idx is not None else count
        if lat is None or lng is None:
            try:
                c_lat = request.form.get(f'gps_lat_{idx_key}', '').strip()
                c_lng = request.form.get(f'gps_lng_{idx_key}', '').strip()
                if c_lat and c_lng:
                    clat, clng = float(c_lat), float(c_lng)
                    if -90 <= clat <= 90 and -180 <= clng <= 180 and not (clat == 0 and clng == 0):
                        lat, lng = clat, clng
            except (ValueError, TypeError):
                pass

        # Fallback: use client-extracted datetime if server EXIF failed
        if taken_at is None:
            try:
                c_dt = request.form.get(f'exif_dt_{idx_key}', '').strip()
                if c_dt:
                    from datetime import datetime as _dt
                    taken_at = _dt.strptime(c_dt[:19], '%Y:%m:%d %H:%M:%S')
            except (ValueError, TypeError):
                pass
        if lat and lng:
            gps_count += 1
        count += 1
        return TourPhoto(
            tour_id  = tour_id,
            user_id  = current_user.id,
            filename = filename,
            caption  = request.form.get('caption', '').strip() or None,
            lat=lat, lng=lng, taken_at=taken_at,
        )

    for file_idx, f in enumerate(files):
        if not f or not f.filename:
            continue
        fname_lower = f.filename.lower()

        # ── ZIP archive ───────────────────────────────────────────────────────
        if fname_lower.endswith('.zip'):
            data = f.read()
            try:
                with _zipfile.ZipFile(_io.BytesIO(data)) as zf:
                    img_names = [
                        n for n in zf.namelist()
                        if not n.startswith('__MACOSX') and not n.startswith('.')
                        and n.rsplit('.', 1)[-1].lower()
                           in app.config['ALLOWED_PHOTO_EXTENSIONS']
                    ]
                    for img_name in img_names:
                        img_data = zf.read(img_name)
                        photo = _process_image_bytes(img_data, img_name)
                        if photo:
                            db.session.add(photo)
                            zip_count += 1
            except Exception as e:
                app.logger.warning(f'ZIP extract failed: {e}')
                skipped += 1
            continue

        # ── Normal image file ─────────────────────────────────────────────────
        if not allowed_file(f.filename, app.config['ALLOWED_PHOTO_EXTENSIONS']):
            skipped += 1
            continue
        photo = _process_image_bytes(f.read(), f.filename, form_idx=file_idx)
        if photo:
            db.session.add(photo)

    db.session.commit()
    parts = [f'{count} Foto(s) hochgeladen']
    if zip_count:
        parts.append(f'📦 davon {zip_count} aus ZIP')
    if gps_count:
        parts.append(f'🗺️ {gps_count} mit GPS')
    if resized:
        parts.append(f'📐 {resized} verkleinert')
    if skipped:
        parts.append(f'{skipped} übersprungen')
    flash(' – '.join(parts), 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#fotos')


@app.route('/touren/<int:tour_id>/teilnehmer/hinzufuegen', methods=['POST'])
@login_required
@organizer_required
def tour_add_participant(tour_id):
    tour = Tour.query.get_or_404(tour_id)
    user_id = request.form.get('user_id', type=int)
    if not user_id:
        flash('Bitte einen Nutzer auswählen.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id))
    user = User.query.get_or_404(user_id)
    existing = TourParticipant.query.filter_by(tour_id=tour_id, user_id=user_id).first()
    if existing:
        existing.status = 'attending'
        flash(f'{user.display_name} ist bereits eingetragen – Status auf „Teilnehmer" gesetzt.', 'info')
    else:
        rsvp = TourParticipant(
            tour_id   = tour_id,
            user_id   = user_id,
            status    = 'attending',
            confirmed_present = request.form.get('confirmed') == '1'
        )
        db.session.add(rsvp)
        flash(f'{user.display_name} wurde zur Tour hinzugefügt.', 'success')
    db.session.commit()
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#teilnehmer')


@app.route('/touren/<int:tour_id>/teilnehmer/<int:user_id>/entfernen', methods=['POST'])
@login_required
@organizer_required
def tour_remove_participant(tour_id, user_id):
    rsvp = TourParticipant.query.filter_by(tour_id=tour_id, user_id=user_id).first_or_404()
    user = User.query.get(user_id)
    db.session.delete(rsvp)
    db.session.commit()
    name = user.display_name if user else 'Nutzer'
    flash(f'{name} wurde von der Tour entfernt.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#teilnehmer')


@app.route('/touren/<int:tour_id>/abschliessen', methods=['POST'])
@login_required
@organizer_required
def tour_complete(tour_id):
    tour = Tour.query.get_or_404(tour_id)
    tour.status = 'completed'
    db.session.commit()
    flash('Tour als abgeschlossen markiert und im Archiv gespeichert.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


@app.route('/touren/<int:tour_id>/bestaetigen', methods=['POST'])
@login_required
@organizer_required
def tour_confirm_participants(tour_id):
    """After tour: set confirmed_present for checked participants."""
    tour = Tour.query.get_or_404(tour_id)
    confirmed_ids = request.form.getlist('confirmed')
    for p in tour.participants:
        p.confirmed_present = str(p.user_id) in confirmed_ids
    db.session.commit()
    flash('Teilnehmer bestätigt.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


# ─── Tour: Edit / Delete ──────────────────────────────────────────────────────

@app.route('/touren/<int:tour_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def tour_edit(tour_id):
    tour = Tour.query.get_or_404(tour_id)
    if not (current_user.is_admin or current_user.is_organizer or
            tour.created_by == current_user.id):
        abort(403)
    if request.method == 'POST':
        tour.title        = request.form.get('title', '').strip()
        tour.description  = request.form.get('description', '').strip() or None
        tour_date_str     = request.form.get('tour_date', '').strip()
        tour.tour_date    = (datetime.strptime(tour_date_str, '%Y-%m-%d').date()
                             if tour_date_str else date(9999, 12, 31))
        tour.start_time   = request.form.get('start_time', '').strip() or None
        tour.difficulty   = request.form.get('difficulty', 'mittel')
        tour.approx_km    = float(request.form['approx_km']) if request.form.get('approx_km') else None
        tour.external_link = request.form.get('external_link', '').strip() or None
        tour.meeting_desc = request.form.get('meeting_desc', '').strip() or None
        try:
            tour.meeting_lat = float(request.form['meeting_lat']) if request.form.get('meeting_lat') else None
            tour.meeting_lng = float(request.form['meeting_lng']) if request.form.get('meeting_lng') else None
        except ValueError:
            pass
        if current_user.is_admin:
            tour.status = request.form.get('status', tour.status)
        db.session.commit()
        flash('Tour aktualisiert.', 'success')
        return redirect(url_for('tour_detail', tour_id=tour.id))
    return render_template('touren/edit.html', tour=tour,
                           difficulties=Config.DIFFICULTY_CHOICES,
                           today=date.today())


@app.route('/touren/<int:tour_id>/loeschen', methods=['POST'])
@login_required
def tour_delete(tour_id):
    tour = Tour.query.get_or_404(tour_id)
    if not (current_user.is_admin or tour.created_by == current_user.id):
        abort(403)
    # Videos vom Dateisystem löschen
    video_dir = app.config.get('UPLOAD_FOLDER_VIDEOS',
                os.path.join(app.root_path, 'static', 'uploads', 'videos'))
    for v in TourVideo.query.filter_by(tour_id=tour_id).all():
        try:
            os.remove(os.path.join(video_dir, v.filename))
        except Exception:
            pass
    # Fotos vom Dateisystem löschen
    for p in TourPhoto.query.filter_by(tour_id=tour_id).all():
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], p.filename))
        except Exception:
            pass
    if tour.gpx_file:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file))
        except Exception:
            pass
    title = tour.title
    db.session.delete(tour)
    db.session.commit()
    flash(f'Tour „{title}" wurde gelöscht.', 'success')
    return redirect(url_for('tour_list'))


@app.route('/admin/tour/<int:tour_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_tour_edit(tour_id):
    return tour_edit(tour_id)


@app.route('/admin/tour/<int:tour_id>/loeschen', methods=['POST'])
@login_required
@admin_required
def admin_tour_delete(tour_id):
    return tour_delete(tour_id)


# ─── Tour photos: bulk delete ─────────────────────────────────────────────────

@app.route('/touren/<int:tour_id>/fotos/bulk-loeschen', methods=['POST'])
@login_required
def photos_bulk_delete(tour_id):
    Tour.query.get_or_404(tour_id)
    count = 0
    for pid in request.form.getlist('photo_ids'):
        photo = TourPhoto.query.get(int(pid))
        if photo and photo.tour_id == tour_id:
            if photo.user_id == current_user.id or current_user.is_admin:
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photo.filename))
                except Exception:
                    pass
                db.session.delete(photo)
                count += 1
    db.session.commit()
    flash(f'{count} Foto(s) gelöscht.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#fotos')


# ─── Tour Video Export ─────────────────────────────────────────────────────────

def _pick_ffmpeg_codec(ffmpeg_bin: str) -> str:
    """Wählt den besten verfügbaren FFmpeg-Videocodec."""
    import subprocess as _sp
    for codec in ['libx264', 'mpeg4', 'libxvid']:
        r = _sp.run(
            [ffmpeg_bin, '-y', '-f', 'lavfi', '-i', 'nullsrc=s=16x16:d=0.1',
             '-c:v', codec, '-f', 'null', '-'],
            capture_output=True, timeout=10
        )
        if r.returncode == 0:
            return codec
    return 'mpeg4'


@app.route('/touren/<int:tour_id>/video')
@login_required
def tour_video(tour_id):
    tour   = Tour.query.get_or_404(tour_id)
    photos = tour.photos.order_by(
        db.text('COALESCE(sort_order, 999999) ASC'), TourPhoto.taken_at.asc().nullslast(), TourPhoto.created_at.asc()
    ).all()
    gpx_data = None
    if tour.gpx_file:
        gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
        if os.path.exists(gpx_path):
            gpx_data = parse_gpx(gpx_path)
    return render_template('touren/video.html',
                           tour=tour, photos=photos,
                           gpx_data=json.dumps(gpx_data) if gpx_data else 'null')


@app.route('/touren/<int:tour_id>/video/render', methods=['POST'])
@login_required
def tour_video_render(tour_id):
    """Server-side MP4 via FFmpeg."""
    import subprocess, tempfile, shutil

    tour   = Tour.query.get_or_404(tour_id)
    photos = tour.photos.order_by(
        db.text('COALESCE(sort_order, 999999) ASC'), TourPhoto.taken_at.asc().nullslast(), TourPhoto.created_at.asc()
    ).all()

    if not photos:
        flash('Keine Fotos – Video benötigt mindestens ein Foto.', 'warning')
        return redirect(url_for('tour_video', tour_id=tour_id))

    # Format aus Formular: landscape=1280x720, portrait=720x1280, square=1080x1080
    fmt = request.form.get('video_format', 'square')
    canvas_map = {
        'landscape': (1280, 720),
        'portrait':  (720, 1280),
        'square':    (1080, 1080),
    }
    cw, ch = canvas_map.get(fmt, (1080, 1080))

    # ffmpeg: erst im Projektordner, dann systemweit
    import shutil
    project_ffmpeg = os.path.join(os.path.dirname(__file__), 'ffmpeg')
    ffmpeg_bin = None
    if os.path.isfile(project_ffmpeg) and os.access(project_ffmpeg, os.X_OK):
        ffmpeg_bin = project_ffmpeg
    if not ffmpeg_bin:
        ffmpeg_bin = shutil.which('ffmpeg')
    if not ffmpeg_bin:
        for candidate in ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg',
                          '/opt/ffmpeg/bin/ffmpeg']:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                ffmpeg_bin = candidate
                break
    if not ffmpeg_bin:
        flash('FFmpeg nicht gefunden. Bitte ffmpeg-Binary ins Projektverzeichnis legen.', 'danger')
        return redirect(url_for('tour_video', tour_id=tour_id))
    app.logger.info(f'FFmpeg gefunden: {ffmpeg_bin}')

    tmpdir = tempfile.mkdtemp(prefix='djo_video_')
    try:
        # ── Fotos in korrekte Ausrichtung bringen (EXIF auto-orient) ─────────
        def auto_orient(src, dst):
            """Dreht das Bild entsprechend EXIF-Orientation-Tag."""
            # 1. Pillow
            try:
                from PIL import Image, ExifTags
                img = Image.open(src)
                exif = img._getexif() or {}
                orient_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
                orient = exif.get(orient_key, 1) if orient_key else 1
                rotations = {3: 180, 6: 270, 8: 90}
                if orient in rotations:
                    img = img.rotate(rotations[orient], expand=True)
                img.save(dst, quality=90)
                return True
            except Exception:
                pass
            # 2. ImageMagick
            try:
                import subprocess as sp
                r = sp.run(['convert', '-auto-orient', src, dst],
                           capture_output=True, timeout=15)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
            # 3. Fallback: Original unverändert
            import shutil as _sh
            _sh.copy2(src, dst)
            return False

        output_path = os.path.join(tmpdir, 'tour.mp4')

        music_file = request.files.get('music')
        music_path = None
        if music_file and music_file.filename:
            ext = music_file.filename.rsplit('.', 1)[-1].lower()
            if ext in ('mp3', 'aac', 'm4a', 'ogg', 'wav', 'flac'):
                music_path = os.path.join(tmpdir, f'music.{ext}')
                music_file.save(music_path)

        photo_dur  = int(request.form.get('photo_duration', 5))
        fps        = 25
        fmt        = request.form.get('video_format', 'portrait')
        if fmt == 'landscape':
            W, H   = 1920, 1080
            SAFE   = 30
        else:  # portrait (default)
            W, H   = 1080, 1920
            SAFE   = 40
        INNER_H    = H - 2 * SAFE

        # ── Jedes Foto vorbereiten (Pillow) ───────────────────────────────────
        # Portrait  → contain auf W×INNER_H, Safe-Area-Padding
        # Landscape → Blur-BG (W×H) + contain FG overlay
        try:
            from PIL import Image as _PIL, ImageFilter as _ILF
            PIL_OK = True
        except Exception:
            PIL_OK = False

        def make_frame(src_path, dst_path):
            """Erstellt ein fertig skaliertes W×H JPEG für FFmpeg."""
            if not PIL_OK:
                import shutil as _sh; _sh.copy2(src_path, dst_path); return
            try:
                img = _PIL.open(src_path).convert('RGB')
                iw, ih = img.size
                is_portrait = ih >= iw

                if is_portrait:
                    # Contain in W×INNER_H, safe area schwarz
                    ratio  = min(W/iw, INNER_H/ih)
                    nw, nh = int(iw*ratio)//2*2, int(ih*ratio)//2*2
                    scaled = img.resize((nw, nh), _PIL.LANCZOS)
                    canvas = _PIL.new('RGB', (W, H), (0, 0, 0))
                    x = (W - nw) // 2
                    y = SAFE + (INNER_H - nh) // 2
                    canvas.paste(scaled, (x, y))
                else:
                    # Blur-Hintergrund: füllt W×H
                    ratio_fill = max(W/iw, H/ih)
                    bw = int(iw * ratio_fill) + 4
                    bh = int(ih * ratio_fill) + 4
                    bg = img.resize((bw, bh), _PIL.LANCZOS)
                    bg = bg.filter(_ILF.GaussianBlur(radius=25))
                    bx = (bw - W) // 2
                    by = (bh - H) // 2
                    canvas = bg.crop((bx, by, bx+W, by+H))
                    # Contain-Foto darüber
                    ratio  = min(W/iw, INNER_H/ih)
                    nw, nh = int(iw*ratio)//2*2, int(ih*ratio)//2*2
                    fg = img.resize((nw, nh), _PIL.LANCZOS)
                    x = (W - nw) // 2
                    y = SAFE + (INNER_H - nh) // 2
                    canvas.paste(fg, (x, y))

                canvas.save(dst_path, 'JPEG', quality=92)
            except Exception as e:
                app.logger.warning(f'make_frame error: {e}', exc_info=True)
                import shutil as _sh; _sh.copy2(src_path, dst_path)

        # ── Fotos verarbeiten ─────────────────────────────────────────────────
        concat_file = os.path.join(tmpdir, 'concat.txt')
        n_valid = 0
        with open(concat_file, 'w') as cf:
            for i, p in enumerate(photos):
                src = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], p.filename)
                if not os.path.exists(src):
                    continue
                oriented = os.path.join(tmpdir, f'oriented_{i:04d}.jpg')
                auto_orient(src, oriented)
                frame = os.path.join(tmpdir, f'frame_{i:04d}.jpg')
                make_frame(oriented, frame)
                cf.write(f"file '{frame}'\nduration {photo_dur}\n")
                n_valid += 1

        if n_valid == 0:
            flash('Foto-Dateien nicht gefunden.', 'danger')
            return redirect(url_for('tour_video', tour_id=tour_id))

        total_secs = n_valid * photo_dur

        # ── Codec wählen ──────────────────────────────────────────────────────
        vcodec = _pick_ffmpeg_codec(ffmpeg_bin)
        codec_opts = (['-c:v', 'libx264', '-preset', 'fast', '-crf', '23']
                      if vcodec == 'libx264' else ['-c:v', vcodec, '-q:v', '5'])

        # vf: Pillow hat die Frames schon vorbereitet (W×H).
        # Als Fallback (falls Pillow fehlschlug): FFmpeg skaliert selbst auf W×H
        vf = (
            f'scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,'
            f'scale=trunc(iw/2)*2:trunc(ih/2)*2,'
            f'pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,'
            f'format=yuv420p'
        )

        if music_path:
            af  = f'afade=t=in:st=0:d=2,afade=t=out:st={max(0,total_secs-3)}:d=3'
            cmd = ([ffmpeg_bin, '-y',
                    '-f', 'concat', '-safe', '0', '-i', concat_file,
                    '-stream_loop', '-1', '-t', str(total_secs), '-i', music_path,
                    '-vf', vf, '-r', str(fps)]
                   + codec_opts
                   + ['-c:a', 'aac', '-b:a', '128k', '-af', af,
                      '-shortest', '-movflags', '+faststart', output_path])
        else:
            cmd = ([ffmpeg_bin, '-y',
                    '-f', 'concat', '-safe', '0', '-i', concat_file,
                    '-vf', vf, '-r', str(fps)]
                   + codec_opts
                   + ['-movflags', '+faststart', output_path])
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            app.logger.error('FFmpeg timeout nach 300s')
            flash('Video-Erstellung hat zu lange gedauert (Timeout).', 'danger')
            return redirect(url_for('tour_video', tour_id=tour_id))
        except Exception as e:
            app.logger.error(f'FFmpeg konnte nicht gestartet werden: {e}')
            flash(f'FFmpeg-Fehler: {e}', 'danger')
            return redirect(url_for('tour_video', tour_id=tour_id))

        if result.returncode != 0:
            stderr = result.stderr.decode(errors='replace')[-1000:]
            app.logger.error(f'FFmpeg exit {result.returncode}: {stderr}')
            flash(f'Video-Erstellung fehlgeschlagen: {stderr[-300:]}', 'danger')
            return redirect(url_for('tour_video', tour_id=tour_id))

        with open(output_path, 'rb') as f:
            video_bytes = f.read()

        safe = ''.join(c for c in tour.title if c.isalnum() or c in ' -_')[:40]
        _date = tour.tour_date.strftime('%Y%m%d') if tour.tour_date else 'keinDatum'
        fname = f'Tour_{safe}_{_date}.mp4'
        resp = make_response(video_bytes)
        resp.headers['Content-Type'] = 'video/mp4'
        resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
        return resp
    except Exception as e:
        app.logger.error(f'tour_video_render unhandled: {e}', exc_info=True)
        flash(f'Unerwarteter Fehler: {e}', 'danger')
        return redirect(url_for('tour_video', tour_id=tour_id))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
# ─── Archiv: add old tour manually ───────────────────────────────────────────

@app.route('/archiv/neu', methods=['GET', 'POST'])
@login_required
@organizer_required
def archiv_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Titel ist erforderlich.', 'danger')
            return redirect(url_for('archiv_new'))
        tour = Tour(
            title        = title,
            description  = request.form.get('description', '').strip() or None,
            tour_date    = datetime.strptime(request.form['tour_date'], '%Y-%m-%d').date(),
            difficulty   = request.form.get('difficulty', 'mittel'),
            status       = 'completed',
            created_by   = current_user.id,
            meeting_desc = request.form.get('meeting_desc', '').strip() or None,
        )
        try:
            tour.gpx_km     = float(request.form['gpx_km'])     if request.form.get('gpx_km')     else None
            tour.gpx_ascent = float(request.form['gpx_ascent']) if request.form.get('gpx_ascent') else None
        except ValueError:
            pass
        db.session.add(tour)
        db.session.commit()

        # GPX-Datei verarbeiten (optional)
        gpx_file = request.files.get('gpx_file')
        if gpx_file and gpx_file.filename and gpx_file.filename.lower().endswith('.gpx'):
            try:
                import secrets as _sec
                os.makedirs(app.config['UPLOAD_FOLDER_GPX'], exist_ok=True)
                gpx_fname = _sec.token_hex(12) + '.gpx'
                gpx_path  = os.path.join(app.config['UPLOAD_FOLDER_GPX'], gpx_fname)
                gpx_file.save(gpx_path)
                parsed = parse_gpx(gpx_path)
                if parsed:
                    tour.gpx_file = gpx_fname
                    if not tour.gpx_km and parsed.get('km'):
                        tour.gpx_km = parsed['km']
                    if not tour.gpx_ascent and parsed.get('ascent'):
                        tour.gpx_ascent = parsed['ascent']
                    db.session.commit()
            except Exception as e:
                app.logger.warning(f'archiv_new GPX upload failed: {e}')

        flash(f'Tour „{tour.title}" ins Archiv eingetragen.', 'success')
        return redirect(url_for('archiv'))
    return render_template('touren/archiv_new.html',
                           difficulties=Config.DIFFICULTY_CHOICES,
                           today=date.today())


# ─── Challenge: bulk delete ───────────────────────────────────────────────────

@app.route('/challenge/fotos/bulk-loeschen', methods=['POST'])
@login_required
def challenge_bulk_delete():
    count = 0
    for pid in request.form.getlist('photo_ids'):
        photo = TourPhoto.query.get(int(pid))
        if photo and (photo.user_id == current_user.id or current_user.is_admin):
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photo.filename))
            except Exception:
                pass
            db.session.delete(photo)
            count += 1
    db.session.commit()
    flash(f'{count} Foto(s) gelöscht.', 'success')
    return redirect(url_for('foto_challenge'))



@app.route('/archiv')
@login_required
def archiv():
    page     = request.args.get('page', 1, type=int)
    PER_PAGE = 20
    q        = _gq(Tour).filter(Tour.status=='completed', Tour.tour_date!=None).order_by(Tour.tour_date.desc())
    total    = q.count()
    tours    = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    pages    = (total + PER_PAGE - 1) // PER_PAGE

    # Teilnehmer- und Fotozahlen in je einer Abfrage (kein N+1)
    tour_ids = [t.id for t in tours]
    part_counts = dict(db.session.query(
        TourParticipant.tour_id,
        db.func.count(TourParticipant.id)
    ).filter(
        TourParticipant.tour_id.in_(tour_ids),
        TourParticipant.confirmed_present == True
    ).group_by(TourParticipant.tour_id).all()) if tour_ids else {}

    photo_counts = dict(db.session.query(
        TourPhoto.tour_id, db.func.count(TourPhoto.id)
    ).filter(TourPhoto.tour_id.in_(tour_ids))
     .group_by(TourPhoto.tour_id).all()) if tour_ids else {}

    # Cover-Fotos
    cover_photos = {}
    if tour_ids:
        first_photos = (TourPhoto.query
                        .filter(TourPhoto.tour_id.in_(tour_ids))
                        .order_by(TourPhoto.tour_id,
                                  db.text('COALESCE(sort_order, 999999) ASC'),
                                  TourPhoto.taken_at.asc().nullslast())
                        .all())
        seen = set()
        for p in first_photos:
            if p.tour_id not in seen:
                cover_photos[p.tour_id] = p
                seen.add(p.tour_id)

    return render_template('touren/archiv.html', tours=tours,
                           part_counts=part_counts, photo_counts=photo_counts,
                           page=page, pages=pages, total=total,
                           cover_photos=cover_photos)


@app.route('/hilfe')
@login_required
def hilfe():
    return render_template('hilfe.html')


@app.route('/api/location/update', methods=['POST'])
@login_required
def location_update():
    """Eigenen Live-Standort aktualisieren."""
    data = request.get_json() or {}
    tour_id  = data.get('tour_id')
    lat      = data.get('lat')
    lng      = data.get('lng')
    accuracy = data.get('accuracy')
    if not all([tour_id, lat, lng]):
        return jsonify({'error': 'missing data'}), 400
    Tour.query.get_or_404(tour_id)
    from datetime import datetime as _dt
    existing = LiveLocation.query.filter_by(
        tour_id=tour_id, user_id=current_user.id
    ).first()
    if existing:
        existing.lat = lat; existing.lng = lng
        existing.accuracy = accuracy
        existing.updated_at = _dt.utcnow()
    else:
        db.session.add(LiveLocation(
            tour_id=tour_id, user_id=current_user.id,
            lat=lat, lng=lng, accuracy=accuracy
        ))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/location/tour/<int:tour_id>')
@login_required
def location_get(tour_id):
    """Alle Live-Standorte einer Tour abrufen (Polling)."""
    from datetime import datetime as _dt, timedelta
    # Nur Standorte die in den letzten 10 Minuten aktualisiert wurden
    cutoff = _dt.utcnow() - timedelta(minutes=10)
    locs = LiveLocation.query.filter(
        LiveLocation.tour_id == tour_id,
        LiveLocation.updated_at >= cutoff
    ).all()
    return jsonify({'locations': [{
        'user_id':  l.user_id,
        'name':     l.user.display_name,
        'lat':      l.lat,
        'lng':      l.lng,
        'accuracy': l.accuracy,
        'ago':      int((_dt.utcnow() - l.updated_at).total_seconds()),
    } for l in locs]})


@app.route('/api/location/stop', methods=['POST'])
@login_required
def location_stop():
    """Eigenen Live-Standort entfernen."""
    data = request.get_json() or {}
    LiveLocation.query.filter_by(
        tour_id=data.get('tour_id'), user_id=current_user.id
    ).delete()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/geplante-touren')
@login_required
def geplante_touren():
    """Geplante Touren ohne fixiertes Datum."""
    touren = (_gq(Tour)
              .filter(Tour.status == 'planned',
                      Tour.tour_date == date(9999, 12, 31))
              .order_by(Tour.created_at.desc())
              .all())

    # GPX-Vorschauen
    gpx_map = {}
    for t in touren:
        if t.gpx_file:
            path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], t.gpx_file)
            if os.path.exists(path):
                parsed = parse_gpx(path)
                if parsed and parsed.get('points'):
                    gpx_map[t.id] = parsed

    # Bewertungen: eine einzige Query für alle Touren (kein N+1)
    tour_ids = [t.id for t in touren]
    all_ratings = (RouteRating.query
                   .filter(RouteRating.tour_id.in_(tour_ids))
                   .all()) if tour_ids else []

    from collections import defaultdict
    ratings_by_tour = defaultdict(list)
    for r in all_ratings:
        ratings_by_tour[r.tour_id].append(r)

    rating_map = {}
    for t in touren:
        ratings = ratings_by_tour[t.id]
        rating_map[t.id] = {
            'good':  sum(1 for r in ratings if r.rating == 'good'),
            'ok':    sum(1 for r in ratings if r.rating == 'ok'),
            'bad':   sum(1 for r in ratings if r.rating == 'bad'),
            'mine':  next((r for r in ratings if r.user_id == current_user.id), None),
            'total': len(ratings),
        }

    return render_template('touren/geplant.html', touren=touren,
                           gpx_map=gpx_map, rating_map=rating_map)


@app.route('/touren/<int:tour_id>/zeitabstimmung', methods=['GET', 'POST'])
@login_required
def tour_time_vote(tour_id):
    """Startzeit-Abstimmung für geplante Touren."""
    tour = Tour.query.get_or_404(tour_id)
    if not tour.is_date_open:
        flash('Zeitabstimmung nur für Touren ohne fixierten Termin.', 'info')
        return redirect(url_for('tour_detail', tour_id=tour_id))

    if request.method == 'POST':
        # Eigene Votes löschen und neu setzen
        TimeVote.query.filter_by(tour_id=tour_id, user_id=current_user.id).delete()
        slots = request.form.getlist('slots')
        for slot in slots:
            if len(slot) == 5 and ':' in slot:  # HH:MM validation
                db.session.add(TimeVote(
                    tour_id=tour_id, user_id=current_user.id, time_slot=slot
                ))
        db.session.commit()
        flash('Deine Verfügbarkeit wurde gespeichert.', 'success')
        return redirect(url_for('tour_time_vote', tour_id=tour_id))

    # Alle Votes laden
    all_votes = TimeVote.query.filter_by(tour_id=tour_id).all()
    my_votes  = {v.time_slot for v in all_votes if v.user_id == current_user.id}

    # Slots aggregieren
    from collections import Counter, defaultdict
    slot_counts  = Counter(v.time_slot for v in all_votes)
    slot_voters  = defaultdict(list)
    for v in all_votes:
        slot_voters[v.time_slot].append(v.user.display_name)

    # Teilnehmer-Count für Quorum
    member_count = _gq(User).filter_by(is_active=True).count()

    # Standard-Slots vorschlagen (06:00 - 11:00)
    default_slots = ['09:00','09:30','10:00','10:30','11:00']

    return render_template('touren/zeitabstimmung.html',
                           tour=tour, my_votes=my_votes,
                           slot_counts=slot_counts, slot_voters=slot_voters,
                           default_slots=default_slots,
                           member_count=member_count)


@app.route('/touren/<int:tour_id>/zeitabstimmung/setzen', methods=['POST'])
@login_required
@organizer_required
def tour_set_time_from_vote(tour_id):
    """Beste Startzeit aus Abstimmung übernehmen."""
    tour = Tour.query.get_or_404(tour_id)
    slot = request.form.get('slot', '').strip()
    if slot and len(slot) == 5 and ':' in slot:
        tour.start_time = slot
        db.session.commit()
        flash(f'Startzeit {slot} Uhr gesetzt.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


@app.route('/touren/<int:tour_id>/bewerten', methods=['POST'])
@login_required
def tour_rate_route(tour_id):
    """Nutzerbewertung einer geplanten Route abgeben oder aktualisieren."""
    Tour.query.get_or_404(tour_id)
    rating  = request.form.get('rating')
    comment = request.form.get('comment', '').strip() or None
    if rating not in ('good', 'ok', 'bad'):
        return jsonify({'ok': False}), 400
    existing = RouteRating.query.filter_by(tour_id=tour_id, user_id=current_user.id).first()
    if existing:
        existing.rating  = rating
        existing.comment = comment
    else:
        db.session.add(RouteRating(tour_id=tour_id, user_id=current_user.id,
                                   rating=rating, comment=comment))
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'ok': True})
    return redirect(request.referrer or url_for('tour_list'))


@app.route('/touren/<int:tour_id>/termin-setzen', methods=['POST'])
@login_required
def tour_set_date(tour_id):
    """Datum und Uhrzeit einer geplanten Tour nachträglich setzen."""
    tour = Tour.query.get_or_404(tour_id)
    if tour.created_by != current_user.id and not current_user.is_admin:
        abort(403)
    date_str = request.form.get('tour_date', '').strip()
    time_str = request.form.get('start_time', '').strip()
    if date_str:
        try:
            from datetime import datetime as dt
            new_date = dt.strptime(date_str, '%Y-%m-%d').date()
            if new_date != date(9999, 12, 31):
                tour.tour_date = new_date
            if time_str:
                tour.start_time = time_str
            db.session.commit()
            flash(f'Termin gesetzt: {new_date.strftime("%d.%m.%Y")}', 'success')
        except ValueError:
            flash('Ungültiges Datum.', 'danger')
    return redirect(url_for('tour_detail', tour_id=tour_id))


@app.route('/suche')
@login_required
def global_search():
    """Globale Suche über Touren, Gastro und Orte."""
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return render_template('suche.html', q=q, results=None)

    like = f'%{q}%'
    tours = _gq(Tour).filter(
        db.or_(
            Tour.title.ilike(like),
            Tour.description.ilike(like),
            Tour.meeting_desc.ilike(like),
            Tour.external_link.ilike(like),
        )
    ).filter(Tour.tour_date != date(9999, 12, 31)).order_by(Tour.tour_date.desc()).limit(10).all()

    # Geplante Touren (ohne Datum) separat
    geplant_hits = _gq(Tour).filter(
        db.or_(Tour.title.ilike(like), Tour.description.ilike(like)),
        Tour.tour_date == date(9999, 12, 31)
    ).limit(5).all()

    gastro = GastroSpot.query.filter(
        db.or_(GastroSpot.name.ilike(like), GastroSpot.address.ilike(like),
                GastroSpot.notes.ilike(like))
    ).limit(10).all()

    from models import POI, TourComment
    pois = POI.query.filter(
        db.or_(POI.name.ilike(like), POI.description.ilike(like))
    ).limit(10).all() if hasattr(POI, 'name') else []

    comments = (TourComment.query
                .filter(TourComment.content.ilike(like))
                .order_by(TourComment.created_at.desc())
                .limit(10).all())

    photo_hits = (TourPhoto.query
                  .filter(TourPhoto.caption.ilike(like),
                          TourPhoto.caption != None)
                  .limit(8).all())

    video_hits = (TourVideo.query
                  .join(Tour, TourVideo.tour_id == Tour.id)
                  .filter(db.or_(TourVideo.title.ilike(like),
                                 TourVideo.description.ilike(like)))
                  .limit(5).all())

    results = {
        'touren':   tours,
        'geplant':  geplant_hits,
        'gastro':   gastro,
        'pois':     pois,
        'comments': comments,
        'photos':   photo_hits,
        'videos':   video_hits,
        'total':    len(tours) + len(geplant_hits) + len(gastro) + len(pois) + len(comments) + len(photo_hits) + len(video_hits),
    }
    return render_template('suche.html', q=q, results=results)


@app.route('/admin/backup', methods=['POST'])
@login_required
def admin_backup():
    """Manuelles Backup aus dem Admin-Dashboard."""
    if not current_user.is_admin:
        abort(403)
    import subprocess
    backup_script = os.path.join(os.path.dirname(__file__), 'backup.sh')
    if not os.path.exists(backup_script):
        flash('backup.sh nicht gefunden.', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        result = subprocess.run(
            ['bash', backup_script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            flash(f'Backup erstellt. {result.stdout.strip()}', 'success')
        else:
            flash(f'Backup-Fehler: {result.stderr[:200]}', 'danger')
    except Exception as e:
        flash(f'Backup fehlgeschlagen: {e}', 'danger')
    return redirect(url_for('admin_dashboard'))


# ─── Admin routes ─────────────────────────────────────────────────────────────
@app.route('/admin/install-packages', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_install_packages():
    """Fehlende Python-Pakete manuell installieren."""
    import subprocess, sys, importlib
    packages = ['pywebpush', 'cryptography']
    results  = []
    # Ziel-Pfad: der venv-Ordner der schon in sys.path ist
    venv_target = next(
        (p for p in sys.path if 'site-packages' in p and os.path.isdir(p)),
        None
    )

    if request.method == 'POST':
        for pkg in packages:
            mod = pkg.replace('-', '_')
            try:
                __import__(mod)
                results.append({'pkg': pkg, 'status': 'already installed', 'ok': True})
                continue
            except ImportError:
                pass
            ok  = False
            log = ''
            # Strategie 1: --target in bekannten site-packages Pfad
            cmds = [[sys.executable, '-m', 'pip', 'install', pkg, '--quiet']]
            if venv_target:
                cmds.insert(0, [sys.executable, '-m', 'pip', 'install', pkg,
                                '--target', venv_target, '--quiet'])
            for cmd in cmds:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    if r.returncode == 0:
                        importlib.invalidate_caches()
                        ok = True
                        break
                    log = r.stderr[-400:]
                except Exception as e:
                    log = str(e)
            results.append({
                'pkg': pkg,
                'status': 'installed' if ok else 'failed',
                'ok': ok,
                'log': '' if ok else log
            })
        flash('Installation abgeschlossen.', 'success' if all(r['ok'] for r in results) else 'warning')
    else:
        for pkg in packages:
            try:
                mod = __import__(pkg.replace('-', '_'))
                location = getattr(mod, '__file__', 'unbekannt')
                results.append({'pkg': pkg, 'status': 'installed', 'ok': True, 'location': location})
            except ImportError:
                results.append({'pkg': pkg, 'status': 'missing', 'ok': False, 'location': ''})

    return render_template('admin/install_packages.html',
                           results=results, venv_target=venv_target)


@app.route('/admin/')
@login_required
@admin_required
def admin_dashboard():
    from datetime import timedelta
    users   = _gq(User).order_by(User.created_at).all()
    invites = _gq(InviteToken).order_by(InviteToken.created_at.desc()).all()

    cutoff_active   = date.today() - timedelta(days=30)
    cutoff_inactive = date.today() - timedelta(days=90)

    active_users   = _gq(User).filter(
        User.last_login >= cutoff_active, User.is_active == True
    ).count()

    inactive_users = _gq(User).filter(
        db.or_(User.last_login < cutoff_inactive, User.last_login == None),
        User.is_active == True
    ).order_by(User.last_login.asc().nullsfirst()).all()

    birthdays = upcoming_birthdays(days=14)

    return render_template('admin/dashboard.html',
                           users=users, invites=invites,
                           active_users=active_users,
                           inactive_users=inactive_users,
                           birthdays=birthdays)


@app.route('/admin/einladung/<int:invite_id>/loeschen', methods=['POST'])
@login_required
@admin_required
def admin_delete_invite(invite_id):
    invite = InviteToken.query.get_or_404(invite_id)
    db.session.delete(invite)
    db.session.commit()
    flash('Einladungslink gelöscht.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/einladen', methods=['POST'])
@login_required
@admin_required
def admin_invite():
    email = request.form.get('email', '').strip().lower()
    label = request.form.get('label', '').strip()
    token = secrets.token_urlsafe(32)
    invite = InviteToken(token=token, email=email or None,
                         label=label or None, created_by=current_user.id)
    db.session.add(invite)
    db.session.commit()
    invite_url = url_for('register', token=token, _external=True)
    label_str  = f' für {label}' if label else ''
    flash(f'Einladungslink{label_str} erstellt: {invite_url}', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/benutzer/<int:user_id>/rolle', methods=['POST'])
@login_required
@admin_required
def admin_set_role(user_id):
    user = User.query.get_or_404(user_id)
    role = request.form.get('role', 'member')
    if role in ('admin', 'organizer', 'member'):
        user.role = role
        db.session.commit()
        flash(f'Rolle von {user.display_name} auf {role} gesetzt.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/benutzer/<int:user_id>/sperren', methods=['POST'])
@login_required
@admin_required
def admin_toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Du kannst dich nicht selbst sperren.', 'warning')
        return redirect(url_for('admin_dashboard'))
    user.is_active = not user.is_active
    db.session.commit()
    status = 'aktiviert' if user.is_active else 'gesperrt'
    flash(f'{user.display_name} wurde {status}.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/benutzer/<int:user_id>/entfernen', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Du kannst dich nicht selbst löschen.', 'warning')
        return redirect(url_for('admin_dashboard'))
    db.session.delete(user)
    db.session.commit()
    flash(f'Benutzer {user.name} wurde entfernt.', 'success')
    return redirect(url_for('admin_dashboard'))


# ─── Phase 2: Gastronomie ─────────────────────────────────────────────────────

GASTRO_TYPES = [
    ('cafe',       '☕ Café'),
    ('baeckerei',  '🥐 Bäckerei'),
    ('kneipe',     '🍺 Kneipe / Gasthaus'),
    ('restaurant', '🍽️ Restaurant'),
    ('imbiss',     '🥪 Imbiss / Kiosk'),
    ('other',      '📍 Sonstiges'),
]

@app.route('/gastro/<int:spot_id>/fotos', methods=['POST'])
@login_required
def gastro_upload_photo(spot_id):
    """Foto zu Gastro-Spot hochladen."""
    spot = GastroSpot.query.get_or_404(spot_id)
    f    = request.files.get('photo')
    if not f or not f.filename:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('gastro_detail', spot_id=spot_id))
    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in app.config['ALLOWED_PHOTO_EXTENSIONS']:
        flash('Nur JPG, PNG, WebP erlaubt.', 'danger')
        return redirect(url_for('gastro_detail', spot_id=spot_id))
    os.makedirs(app.config['UPLOAD_FOLDER_PHOTOS'], exist_ok=True)
    filename = f'gastro_{spot_id}_{secrets.token_hex(6)}.{ext}'
    save_path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], filename)
    f.save(save_path)
    _resize_photo_if_needed(save_path)
    caption = request.form.get('caption', '').strip() or None
    photo = GastroPhoto(spot_id=spot_id, user_id=current_user.id,
                        filename=filename, caption=caption)
    db.session.add(photo)
    db.session.commit()
    flash('Foto hochgeladen.', 'success')
    return redirect(url_for('gastro_detail', spot_id=spot_id))


@app.route('/gastro/fotos/<int:photo_id>/loeschen', methods=['POST'])
@login_required
def gastro_delete_photo(photo_id):
    """Gastro-Foto löschen."""
    photo = GastroPhoto.query.get_or_404(photo_id)
    if not (current_user.is_admin or current_user.is_organizer or
            photo.user_id == current_user.id):
        abort(403)
    path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photo.filename)
    if os.path.exists(path):
        os.remove(path)
    spot_id = photo.spot_id
    db.session.delete(photo)
    db.session.commit()
    flash('Foto gelöscht.', 'success')
    return redirect(url_for('gastro_detail', spot_id=spot_id))


@app.route('/gastro')
@login_required
def gastro_list():
    morning_only = request.args.get('morning') == '1'
    typ          = request.args.get('type', '')
    q            = request.args.get('q', '').strip()

    # Persönliche Schwelle zuerst, dann Site-Config, dann Fallback
    morning_threshold = (current_user.morning_opener_until
                         or cfg('morning_opener_until') or '09:30')
    # Aus dem Formular überschreiben und für nächstes Mal speichern
    form_thresh = request.args.get('morning_until', '').strip()
    if form_thresh and len(form_thresh) == 5:
        morning_threshold = form_thresh
        if form_thresh != (current_user.morning_opener_until or ''):
            current_user.morning_opener_until = form_thresh
            db.session.commit()

    spots = GastroSpot.query
    if q:
        spots = spots.filter(GastroSpot.name.ilike(f'%{q}%'))
    if typ:
        spots = spots.filter_by(spot_type=typ)
    if morning_only:
        spots = spots.filter(
            GastroSpot.opens_at != None,
            GastroSpot.opens_at <= morning_threshold
        )
    spots = spots.order_by(GastroSpot.name).all()
    return render_template('gastro/list.html', spots=spots,
                           gastro_types=GASTRO_TYPES,
                           morning_only=morning_only, typ=typ, q=q,
                           morning_threshold=morning_threshold)


@app.route('/gastro/neu', methods=['GET', 'POST'])
@login_required
def gastro_new():
    if request.method == 'POST':
        spot = GastroSpot(
            name       = request.form.get('name','').strip(),
            spot_type  = request.form.get('spot_type','cafe'),
            address    = request.form.get('address','').strip() or None,
            lat        = float(request.form.get('lat',0)),
            lng        = float(request.form.get('lng',0)),
            opens_at   = request.form.get('opens_at','') or None,
            closes_at  = request.form.get('closes_at','') or None,
            phone      = request.form.get('phone','').strip() or None,
            website    = request.form.get('website','').strip() or None,
            notes      = request.form.get('notes','').strip() or None,
            added_by   = current_user.id,
        )
        db.session.add(spot)
        db.session.commit()
        flash(f'"{spot.name}" wurde hinzugefügt!', 'success')
        return redirect(url_for('gastro_detail', spot_id=spot.id))
    return render_template('gastro/form.html', spot=None, gastro_types=GASTRO_TYPES)


@app.route('/gastro/<int:spot_id>')
@login_required
def gastro_detail(spot_id):
    spot    = GastroSpot.query.get_or_404(spot_id)
    reviews = GastroReview.query.filter_by(spot_id=spot_id).order_by(GastroReview.created_at.desc()).all()
    my_rev  = GastroReview.query.filter_by(spot_id=spot_id, user_id=current_user.id).first()
    photos  = GastroPhoto.query.filter_by(spot_id=spot_id).order_by(GastroPhoto.created_at).all()
    places_key = cfg('google_places_api_key') or ''
    return render_template('gastro/detail.html', spot=spot,
                           reviews=reviews, my_rev=my_rev,
                           photos=photos, places_key=places_key)


@app.route('/gastro/<int:spot_id>/bewerten', methods=['POST'])
@login_required
def gastro_review(spot_id):
    GastroSpot.query.get_or_404(spot_id)
    score = request.form.get('score')
    emoji = request.form.get('emoji','').strip()
    note  = request.form.get('note','').strip()

    existing = GastroReview.query.filter_by(spot_id=spot_id, user_id=current_user.id).first()
    if existing:
        existing.score = int(score) if score else None
        existing.emoji = emoji or None
        existing.note  = note or None
    else:
        rev = GastroReview(
            spot_id = spot_id,
            user_id = current_user.id,
            score   = int(score) if score else None,
            emoji   = emoji or None,
            note    = note or None,
        )
        db.session.add(rev)
    db.session.commit()
    flash('Bewertung gespeichert!', 'success')
    return redirect(url_for('gastro_detail', spot_id=spot_id))


@app.route('/gastro/<int:spot_id>/loeschen', methods=['POST'])
@login_required
def gastro_delete(spot_id):
    spot = GastroSpot.query.get_or_404(spot_id)
    if spot.added_by != current_user.id and not current_user.is_admin:
        abort(403)
    db.session.delete(spot)
    db.session.commit()
    flash('Eintrag gelöscht.', 'success')
    return redirect(url_for('gastro_list'))


@app.route('/gastro/<int:spot_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def gastro_edit(spot_id):
    spot = GastroSpot.query.get_or_404(spot_id)
    if spot.added_by != current_user.id and not current_user.is_admin:
        abort(403)
    if request.method == 'POST':
        spot.name      = request.form.get('name', '').strip()
        spot.spot_type = request.form.get('spot_type', 'other')
        spot.address   = request.form.get('address', '').strip() or None
        spot.opens_at  = request.form.get('opens_at', '').strip() or None
        spot.closes_at = request.form.get('closes_at', '').strip() or None
        spot.phone     = request.form.get('phone', '').strip() or None
        spot.website   = request.form.get('website', '').strip() or None
        spot.notes     = request.form.get('notes', '').strip() or None
        try:
            spot.lat = float(request.form.get('lat'))
            spot.lng = float(request.form.get('lng'))
        except (TypeError, ValueError):
            flash('Ungültige Koordinaten.', 'danger')
            return render_template('gastro/form.html', spot=spot, gastro_types=GASTRO_TYPES)
        if not spot.name:
            flash('Name ist erforderlich.', 'danger')
            return render_template('gastro/form.html', spot=spot, gastro_types=GASTRO_TYPES)
        db.session.commit()
        flash('Eintrag aktualisiert.', 'success')
        return redirect(url_for('gastro_detail', spot_id=spot.id))
    return render_template('gastro/form.html', spot=spot, gastro_types=GASTRO_TYPES)



@app.route('/api/gastro/<int:spot_id>/places-lookup')
@login_required
def gastro_places_lookup(spot_id):
    """Search Google Places API for a gastro spot and return structured data."""
    spot = GastroSpot.query.get_or_404(spot_id)
    api_key = cfg('google_places_api_key', '').strip()
    if not api_key:
        return jsonify({'error': 'Kein Google Places API-Key konfiguriert.'}), 400
    try:
        q = f"{spot.name} {spot.address or ''}".strip()
        # Text search to get place_id
        search_resp = http_requests.get(
            'https://maps.googleapis.com/maps/api/place/textsearch/json',
            params={'query': q, 'location': f'{spot.lat},{spot.lng}',
                    'radius': 500, 'language': 'de', 'key': api_key},
            timeout=10
        )
        search_data = search_resp.json()
        if not search_data.get('results'):
            return jsonify({'results': []})
        # Get details for top 3 results
        results = []
        for place in search_data['results'][:3]:
            pid = place.get('place_id')
            det = http_requests.get(
                'https://maps.googleapis.com/maps/api/place/details/json',
                params={'place_id': pid, 'language': 'de',
                        'fields': 'name,formatted_address,formatted_phone_number,website,opening_hours,geometry',
                        'key': api_key},
                timeout=10
            ).json().get('result', {})
            oh = det.get('opening_hours', {})
            opens_at = closes_at = None
            if oh.get('periods'):
                for p in oh['periods']:
                    if p.get('open', {}).get('day') == 1:  # Monday as reference
                        opens_at  = p['open'].get('time', '')[:2] + ':' + p['open'].get('time', '')[2:]
                        closes_at = p.get('close', {}).get('time', '')
                        if closes_at:
                            closes_at = closes_at[:2] + ':' + closes_at[2:]
                        break
            results.append({
                'name':     det.get('name', place.get('name', '')),
                'address':  det.get('formatted_address', ''),
                'phone':    det.get('formatted_phone_number', ''),
                'website':  det.get('website', ''),
                'opens_at':  opens_at or '',
                'closes_at': closes_at or '',
                'weekday_text': oh.get('weekday_text', []),
            })
        return jsonify({'results': results})
    except Exception as e:
        app.logger.error(f'Google Places error: {e}')
        return jsonify({'error': str(e)}), 502


@app.route('/gastro/<int:spot_id>/import', methods=['POST'])
@login_required
def gastro_import(spot_id):
    """Import selected fields from external lookup into the gastro spot."""
    spot = GastroSpot.query.get_or_404(spot_id)
    if spot.added_by != current_user.id and not current_user.is_admin:
        abort(403)
    fields = request.json or {}
    if 'name'      in fields and fields['name']:     spot.name     = fields['name']
    if 'address'   in fields and fields['address']:  spot.address  = fields['address']
    if 'phone'     in fields and fields['phone']:    spot.phone    = fields['phone']
    if 'website'   in fields and fields['website']:  spot.website  = fields['website']
    if 'opens_at'  in fields and fields['opens_at']: spot.opens_at = fields['opens_at']
    if 'closes_at' in fields and fields['closes_at']:spot.closes_at= fields['closes_at']
    db.session.commit()
    return jsonify({'ok': True})



@app.route('/touren/<int:tour_id>/videos', methods=['POST'])
@login_required
def tour_upload_video(tour_id):
    """MP4/Video-Datei zu einer Tour hochladen – direkt auf Disk streamen."""
    import traceback as _tb
    tour = Tour.query.get_or_404(tour_id)

    try:
        f = request.files.get('video')
        app.logger.info(f'Video upload: files={list(request.files.keys())}, f={f}, filename={f.filename if f else None}')

        if not f or not f.filename:
            flash('Keine Datei ausgewählt.', 'danger')
            return redirect(url_for('tour_detail', tour_id=tour_id) + '#videos')

        ext = f.filename.rsplit('.', 1)[-1].lower()
        allowed_video = app.config.get('ALLOWED_VIDEO_EXTENSIONS', {'mp4','mov','avi','mkv','m4v'})
        video_folder  = app.config.get('UPLOAD_FOLDER_VIDEOS',
                         os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'videos'))
        max_video     = app.config.get('MAX_VIDEO_SIZE', 500 * 1024 * 1024)
        app.logger.info(f'Video ext={ext}, allowed={allowed_video}')

        if ext not in allowed_video:
            flash(f'Dateityp .{ext} nicht erlaubt. Nur MP4, MOV, AVI, MKV, M4V.', 'danger')
            return redirect(url_for('tour_detail', tour_id=tour_id) + '#videos')

        video_folder_use = video_folder
        app.logger.info(f'Video folder: {video_folder_use}')
        os.makedirs(video_folder_use, exist_ok=True)

        filename  = f'{tour_id}_{secrets.token_hex(8)}.{ext}'
        save_path = os.path.join(video_folder_use, filename)
        app.logger.info(f'Saving to: {save_path}')

        f.save(save_path)
        filesize = os.path.getsize(save_path)
        app.logger.info(f'Saved: {filesize} bytes')

        # Faststart: moov-Atom an den Anfang verschieben für Browser-Streaming
        # Ohne faststart lädt der Browser die ganze Datei bevor er startet
        try:
            _ffmpeg = None
            _proj   = os.path.join(os.path.dirname(__file__), 'ffmpeg')
            if os.path.isfile(_proj) and os.access(_proj, os.X_OK):
                _ffmpeg = _proj
            else:
                import shutil as _sh
                _ffmpeg = _sh.which('ffmpeg')
            if _ffmpeg:
                _faststart_path = save_path + '.fast.mp4'
                _result = subprocess.run(
                    [_ffmpeg, '-y', '-i', save_path,
                     '-c', 'copy', '-movflags', '+faststart',
                     _faststart_path],
                    capture_output=True, timeout=120
                )
                if _result.returncode == 0 and os.path.exists(_faststart_path):
                    os.replace(_faststart_path, save_path)
                    filesize = os.path.getsize(save_path)
                    app.logger.info('Faststart applied')
                else:
                    app.logger.warning('Faststart failed: ' + _result.stderr.decode()[:200])
        except Exception as _fe:
            app.logger.warning(f'Faststart skipped: {_fe}')

        if filesize > max_video:
            os.remove(save_path)
            flash('Video zu groß (max. 500 MB).', 'danger')
            return redirect(url_for('tour_detail', tour_id=tour_id) + '#videos')

        title = request.form.get('video_title', '').strip() or f.filename
        video = TourVideo(
            tour_id=tour_id, user_id=current_user.id,
            filename=filename, title=title, filesize=filesize
        )
        db.session.add(video)
        db.session.commit()
        mb = round(filesize / 1024 / 1024, 1)
        flash(f'Video "{title}" hochgeladen ({mb} MB).', 'success')
        return redirect(url_for('tour_detail', tour_id=tour_id) + '#videos')

    except Exception as e:
        tb = _tb.format_exc()
        app.logger.error(f'Video upload error: {tb}')
        flash(f'Upload-Fehler: {type(e).__name__}: {e}', 'danger')
        return redirect(url_for('tour_detail', tour_id=tour_id) + '#videos')


@app.route('/videos/<int:video_id>/loeschen', methods=['POST'])
@login_required
def tour_delete_video(video_id):
    """Video löschen."""
    video = TourVideo.query.get_or_404(video_id)
    tour  = Tour.query.get(video.tour_id)
    if not (current_user.is_admin or current_user.is_organizer
            or video.user_id == current_user.id
            or (tour and tour.created_by == current_user.id)):
        abort(403)
    path = os.path.join(app.config.get('UPLOAD_FOLDER_VIDEOS', os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'videos')), video.filename)
    if os.path.exists(path):
        os.remove(path)
    tour_id = video.tour_id
    db.session.delete(video)
    db.session.commit()
    flash('Video gelöscht.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#videos')


@app.route('/videos/file/<path:filename>')
@login_required
def serve_video(filename):
    """Videos für eingeloggte Nutzer ausliefern."""
    folder = app.config.get('UPLOAD_FOLDER_VIDEOS',
             os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'videos'))
    # Sicherstellen dass Ordner existiert
    os.makedirs(folder, exist_ok=True)
    ext  = filename.rsplit('.', 1)[-1].lower()
    mime = {'mp4':'video/mp4','mov':'video/mp4','m4v':'video/mp4',
            'avi':'video/x-msvideo','mkv':'video/x-matroska'}.get(ext, 'video/mp4')
    return send_from_directory(folder, filename, mimetype=mime,
                               conditional=True)


@app.route('/fotos/img/<path:filename>')
@login_required
def serve_photo(filename):
    """Fotos nur fuer eingeloggte Nutzer servieren."""
    return send_from_directory(app.config['UPLOAD_FOLDER_PHOTOS'], filename)


# ─── Phase 2: POIs (Pausenorte & Lieblingsorte) ───────────────────────────────

POI_CATEGORIES = [
    ('pausenort',   '☕ Pausenort'),
    ('lieblingsort','❤️ Lieblingsort'),
    ('bank',        '🪑 Bank / Sitzgelegenheit'),
    ('brunnen',     '💧 Brunnen / Wasser'),
    ('wc',          '🚻 WC'),
    ('aussicht',    '🏔️ Aussichtspunkt'),
    ('reparatur',   '🔧 Fahrrad-Reparatur'),
]

@app.route('/orte')
@login_required
def poi_list():
    cat  = request.args.get('cat','')
    pois = POI.query.filter(
        (POI.is_shared == True) | (POI.added_by == current_user.id)
    )
    if cat:
        pois = pois.filter_by(category=cat)
    pois = pois.order_by(POI.category, POI.name).all()
    return render_template('orte/list.html', pois=pois,
                           poi_categories=POI_CATEGORIES, cat=cat)


@app.route('/orte/neu', methods=['GET', 'POST'])
@login_required
def poi_new():
    if request.method == 'POST':
        poi = POI(
            name        = request.form.get('name','').strip(),
            category    = request.form.get('category','pausenort'),
            lat         = float(request.form.get('lat', 0)),
            lng         = float(request.form.get('lng', 0)),
            description = request.form.get('description','').strip() or None,
            is_shared   = request.form.get('is_shared','1') == '1',
            added_by    = current_user.id,
        )
        db.session.add(poi)
        db.session.commit()
        flash(f'"{poi.name}" wurde gespeichert!', 'success')
        return redirect(url_for('poi_list'))
    return render_template('orte/form.html', poi=None, poi_categories=POI_CATEGORIES)


@app.route('/orte/<int:poi_id>/loeschen', methods=['POST'])
@login_required
def poi_delete(poi_id):
    poi = POI.query.get_or_404(poi_id)
    if poi.added_by != current_user.id and not current_user.is_admin:
        abort(403)
    db.session.delete(poi)
    db.session.commit()
    flash('Ort gelöscht.', 'success')
    return redirect(url_for('poi_list'))


# ─── Phase 2: Globale Karte ───────────────────────────────────────────────────

@app.route('/karte')
@login_required
def global_map():
    # Collect all geo-tagged data for the map
    pois = POI.query.filter(
        (POI.is_shared == True) | (POI.added_by == current_user.id)
    ).all()
    gastro = GastroSpot.query.all()
    tours  = _gq(Tour).filter(
        Tour.meeting_lat != None
    ).filter(Tour.tour_date!=None).order_by(Tour.tour_date.desc()).limit(30).all()

    pois_json   = json.dumps([{
        'id': p.id, 'name': p.name, 'cat': p.category,
        'icon': p.category_icon, 'label': p.category_label,
        'lat': p.lat, 'lng': p.lng, 'desc': p.description or ''
    } for p in pois])

    gastro_json = json.dumps([{
        'id': g.id, 'name': g.name, 'type': g.type_label,
        'lat': g.lat, 'lng': g.lng,
        'opens': g.opens_at or '', 'closes': g.closes_at or '',
        'morning': g.is_morning_friendly,
        'rating': g.avg_rating,
        'notes': g.notes or ''
    } for g in gastro])

    meetings_json = json.dumps([{
        'id': t.id, 'title': t.title,
        'lat': t.meeting_lat, 'lng': t.meeting_lng,
        'desc': t.meeting_desc or '',
        'date': t.tour_date.strftime('%d.%m.%Y') if t.tour_date else 'offen',
        'status': t.status
    } for t in tours if t.meeting_lat])

    return render_template('karte.html',
                           pois_json=pois_json,
                           gastro_json=gastro_json,
                           meetings_json=meetings_json,
                           poi_categories=POI_CATEGORIES,
                           gastro_types=GASTRO_TYPES,
                           morning_threshold=(current_user.morning_opener_until
                                              or cfg('morning_opener_until') or '09:30'))


# ─── Phase 2: Weather API proxy ───────────────────────────────────────────────

@app.route('/api/wetter')
@login_required
def api_wetter():
    """Proxy Open-Meteo: Tagesprognose + stündliche Daten für Tourstartzeit."""
    lat   = request.args.get('lat', '53.1')
    lng   = request.args.get('lng', '9.2')
    dt    = request.args.get('date', '')
    hour  = request.args.get('hour', '9')   # Tour-Startzeit als Stunde

    if not dt:
        return jsonify({'error': 'date required'}), 400

    # WMO code → emoji + label
    def wmo_label(c):
        if c == 0:   return '☀️', 'Sonnig'
        if c <= 2:   return '🌤️', 'Überwiegend sonnig'
        if c == 3:   return '☁️', 'Bewölkt'
        if c <= 49:  return '🌫️', 'Nebel / Dunst'
        if c <= 57:  return '🌧️', 'Nieselregen'
        if c <= 67:  return '🌧️', 'Regen'
        if c <= 77:  return '🌨️', 'Schnee'
        if c <= 82:  return '🌦️', 'Regenschauer'
        if c <= 86:  return '🌨️', 'Schneeschauer'
        if c <= 99:  return '⛈️', 'Gewitter'
        return '🌡️', 'Unbekannt'

    def wind_dir(deg):
        dirs = ['N','NO','O','SO','S','SW','W','NW']
        return dirs[round(deg / 45) % 8]

    try:
        resp = http_requests.get(
            'https://api.open-meteo.com/v1/forecast',
            params={
                'latitude':   lat,
                'longitude':  lng,
                'daily':      'weathercode,temperature_2m_max,temperature_2m_min,'
                              'precipitation_sum,windspeed_10m_max,windgusts_10m_max,'
                              'precipitation_probability_max,winddirection_10m_dominant,'
                              'uv_index_max',
                'hourly':     'temperature_2m,precipitation_probability,windspeed_10m,'
                              'winddirection_10m,weathercode,cloudcover',
                'timezone':   'Europe/Berlin',
                'start_date': dt,
                'end_date':   dt,
                'wind_speed_unit': 'kmh',
            },
            timeout=8
        )
        data = resp.json()
        if 'daily' not in data:
            return jsonify({'error': 'no data'}), 502

        d   = data['daily']
        h   = data.get('hourly', {})
        idx = 0

        wcode           = d['weathercode'][idx]
        icon, label     = wmo_label(wcode)
        wind_deg        = d.get('winddirection_10m_dominant', [None])[idx]
        wind_dir_str    = wind_dir(wind_deg) if wind_deg is not None else ''
        uv              = d.get('uv_index_max', [None])[idx]

        # Stündliche Daten für Startzeit
        target_hour = int(hour)
        hourly_data = {}
        if h and 'time' in h:
            for i, t in enumerate(h['time']):
                t_hour = int(t.split('T')[1][:2])
                if t_hour == target_hour:
                    hw       = h.get('weathercode', [None])[i]
                    h_icon, h_label = wmo_label(hw) if hw is not None else ('', '')
                    hwd      = h.get('winddirection_10m', [None])[i]
                    hourly_data = {
                        'temp':     h.get('temperature_2m', [None])[i],
                        'rain_pct': h.get('precipitation_probability', [None])[i],
                        'wind':     h.get('windspeed_10m', [None])[i],
                        'wind_dir': wind_dir(hwd) if hwd is not None else '',
                        'cloud':    h.get('cloudcover', [None])[i],
                        'icon':     h_icon,
                        'label':    h_label,
                    }
                    break

        return jsonify({
            'icon':        icon,
            'label':       label,
            'temp_max':    d['temperature_2m_max'][idx],
            'temp_min':    d['temperature_2m_min'][idx],
            'rain_mm':     d['precipitation_sum'][idx],
            'rain_pct':    d['precipitation_probability_max'][idx],
            'wind_kmh':    d['windspeed_10m_max'][idx],
            'wind_gusts':  d.get('windgusts_10m_max', [None])[idx],
            'wind_dir':    wind_dir_str,
            'uv':          uv,
            'hourly':      hourly_data,
        })
    except Exception as e:
        app.logger.error(f'Weather API error: {e}')
        return jsonify({'error': str(e)}), 502


@app.route('/api/wetter/verlauf')
@login_required
def api_wetter_verlauf():
    """Stündlicher Tagesverlauf für ein Datum (für Chart)."""
    lat = request.args.get('lat', '53.1')
    lng = request.args.get('lng', '9.2')
    dt  = request.args.get('date', '')
    if not dt:
        return jsonify({'error': 'date required'}), 400
    try:
        resp = http_requests.get(
            'https://api.open-meteo.com/v1/forecast',
            params={
                'latitude':   lat,
                'longitude':  lng,
                'hourly':     'temperature_2m,precipitation_probability,'
                              'windspeed_10m,weathercode,precipitation',
                'timezone':   'Europe/Berlin',
                'start_date': dt,
                'end_date':   dt,
                'wind_speed_unit': 'kmh',
            },
            timeout=8
        )
        data = resp.json()
        h = data.get('hourly', {})
        if not h or 'time' not in h:
            return jsonify({'error': 'no hourly data'}), 502

        def wmo_icon(c):
            if c == 0:  return '☀️'
            if c <= 2:  return '🌤️'
            if c == 3:  return '☁️'
            if c <= 49: return '🌫️'
            if c <= 67: return '🌧️'
            if c <= 77: return '🌨️'
            if c <= 82: return '🌦️'
            if c <= 99: return '⛈️'
            return '🌡️'

        hours = []
        for i, t in enumerate(h['time']):
            hour = int(t.split('T')[1][:2])
            wc = (h.get('weathercode') or [None])[i]
            hours.append({
                'hour':  hour,
                'temp':  (h.get('temperature_2m') or [None])[i],
                'rain':  (h.get('precipitation_probability') or [None])[i],
                'precip':(h.get('precipitation') or [0])[i],
                'wind':  (h.get('windspeed_10m') or [None])[i],
                'icon':  wmo_icon(wc) if wc is not None else '',
            })
        return jsonify({'hours': hours})
    except Exception as e:
        app.logger.error(f'Weather verlauf error: {e}')
        return jsonify({'error': str(e)}), 502


# ─── Phase 2: Overpass API proxy (Gastro entlang Route) ──────────────────────

@app.route('/api/overpass-gastro')
@login_required
def api_overpass_gastro():
    """Search OSM for amenities in a bounding box."""
    try:
        s = float(request.args.get('s'))
        w = float(request.args.get('w'))
        n = float(request.args.get('n'))
        e = float(request.args.get('e'))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid bbox'}), 400

    # Limit bbox size – at zoom 13+ the span stays well below 0.15°
    if (n - s) > 0.5 or (e - w) > 0.5:
        return jsonify({'error': 'bbox too large'}), 400

    query = f"""
[out:json][timeout:15];
(
  node["amenity"~"cafe|bar|pub|restaurant|fast_food|bakery|biergarten"]
      ({s},{w},{n},{e});
  way["amenity"~"cafe|bar|pub|restaurant|fast_food|bakery|biergarten"]
      ({s},{w},{n},{e});
);
out center 60;
"""
    OVERPASS_ENDPOINTS = [
        'https://overpass-api.de/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter',
    ]
    last_error = 'Unbekannter Fehler'
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            resp = http_requests.post(endpoint, data={'data': query}, timeout=20)
            if resp.status_code != 200:
                last_error = f'HTTP {resp.status_code}'
                app.logger.warning(f'Overpass {endpoint} -> {resp.status_code}')
                continue
            try:
                data = resp.json()
            except ValueError:
                preview = resp.text[:200] if resp.text else '(leer)'
                last_error = f'Kein JSON: {preview}'
                app.logger.error(f'Overpass JSON-Fehler ({endpoint}): {preview}')
                continue
            results = []
            for el in data.get('elements', []):
                tags = el.get('tags', {})
                lat  = el.get('lat') or el.get('center', {}).get('lat')
                lng  = el.get('lon') or el.get('center', {}).get('lon')
                if not lat or not lng:
                    continue
                name = tags.get('name') or tags.get('amenity', 'Unbekannt')
                results.append({
                    'osm_id':  str(el.get('id', '')),
                    'name':    name,
                    'type':    tags.get('amenity', ''),
                    'lat':     lat,
                    'lng':     lng,
                    'opening_hours': tags.get('opening_hours', ''),
                    'phone':   tags.get('phone', ''),
                    'website': tags.get('website', ''),
                })
            return jsonify({'results': results})
        except http_requests.exceptions.Timeout:
            last_error = f'Timeout bei {endpoint}'
            app.logger.warning(last_error)
            continue
        except Exception as e:
            last_error = str(e)
            app.logger.error(f'Overpass error ({endpoint}): {e}')
            continue
    return jsonify({'error': f'Overpass nicht erreichbar: {last_error}'}), 502


# ─── Phase 2: Telegram reminder CLI ──────────────────────────────────────────

@app.cli.command('send-reminders')
def send_reminders():
    """Send Telegram reminders for tomorrow's tours. Run via cron daily."""
    from datetime import timedelta
    tomorrow = date.today() + timedelta(days=1)
    tours = _gq(Tour).filter_by(tour_date=tomorrow, status='planned').all()
    if not tours:
        print('Keine Touren morgen.')
        return
    for t in tours:
        attending = TourParticipant.query.filter_by(tour_id=t.id, status='attending').count()
        msg = (
            f'⏰ <b>Erinnerung: Morgen ist Tourtag!</b>\n\n'
            f'🚴 <b>{t.title}</b>\n'
            f'📅 {t.tour_date.strftime("%d.%m.%Y") if t.tour_date else "Datum offen"}'
            f'{" um " + t.start_time + " Uhr" if t.start_time else ""}\n'
            f'👥 {attending} Teilnehmer angemeldet\n'
        )
        if t.meeting_desc:
            msg += f'📍 Treffpunkt: {t.meeting_desc}\n'
        msg += f'\n👉 {app.config["BASE_URL"]}/touren/{t.id}'
        send_telegram(msg)
        print(f'Reminder gesendet: {t.title}')


# ─── Phase 3: Kommentare ─────────────────────────────────────────────────────

@app.route('/touren/<int:tour_id>/kommentieren', methods=['POST'])
@login_required
def tour_comment(tour_id):
    Tour.query.get_or_404(tour_id)
    content   = request.form.get('content','').strip()
    parent_id = request.form.get('parent_id') or None
    if not content:
        flash('Kommentar darf nicht leer sein.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id))

    comment = TourComment(
        tour_id   = tour_id,
        user_id   = current_user.id,
        content   = content,
        parent_id = int(parent_id) if parent_id else None
    )
    db.session.add(comment)
    db.session.commit()
    flash('Kommentar gespeichert.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#kommentare')


@app.route('/touren/<int:tour_id>/kommentare/<int:comment_id>/loeschen', methods=['POST'])
@login_required
def comment_delete(tour_id, comment_id):
    comment = TourComment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    flash('Kommentar gelöscht.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#kommentare')


# ─── Phase 3: Badges (dynamisch berechnet) ───────────────────────────────────

BADGE_DEFINITIONS = [
    # (id, icon, label, description, check_fn)
    ('first_tour',   '🚴', 'Erste Fahrt',       'An der ersten Tour teilgenommen',         lambda c,km: c >= 1),
    ('tours_5',      '🌟', '5 Touren',           '5 Touren mitgefahren',                    lambda c,km: c >= 5),
    ('tours_10',     '🏅', '10 Touren',          '10 Touren mitgefahren',                   lambda c,km: c >= 10),
    ('tours_25',     '🏆', '25 Touren',          '25 Touren mitgefahren – echter Stamm!',   lambda c,km: c >= 25),
    ('tours_50',     '👑', '50 Touren',          'Legende: 50 Touren dabei',                lambda c,km: c >= 50),
    ('km_100',       '💯', '100 km',             '100 km Gesamtstrecke',                    lambda c,km: km >= 100),
    ('km_500',       '🚀', '500 km',             '500 km Gesamtstrecke',                    lambda c,km: km >= 500),
    ('km_1000',      '🌍', '1.000 km',           '1.000 km – Weltumradler!',                lambda c,km: km >= 1000),
    ('km_2500',      '🛸', '2.500 km',           '2.500 km Gesamtstrecke',                  lambda c,km: km >= 2500),
]

def compute_badges(user):
    """Return list of earned badge dicts for a user."""
    confirmed = TourParticipant.query.filter_by(
        user_id=user.id, confirmed_present=True
    ).all()
    tour_count = len(confirmed)
    total_km   = sum(
        tp.tour.gpx_km for tp in confirmed
        if tp.tour and tp.tour.gpx_km
    )
    earned = []
    for bid, icon, label, desc, check in BADGE_DEFINITIONS:
        if check(tour_count, total_km):
            earned.append({'id':bid, 'icon':icon, 'label':label, 'desc':desc})
    return earned


def user_stats(user):
    """Return dict of aggregated stats for a user – optimiert mit JOIN."""
    from sqlalchemy.orm import joinedload
    from datetime import datetime as _dt
    all_part = (TourParticipant.query
                .filter_by(user_id=user.id, status='attending')
                .options(joinedload(TourParticipant.tour))
                .all())
    confirmed    = [p for p in all_part if p.confirmed_present and p.tour
                    and p.tour.tour_date and not p.tour.is_date_open]
    this_year    = _dt.now().year
    this_year_tours = [p for p in confirmed
                       if p.tour.tour_date and p.tour.tour_date.year == this_year]
    total_km     = sum(p.tour.gpx_km  or p.tour.approx_km or 0 for p in confirmed)
    total_ascent = sum(p.tour.gpx_ascent or 0 for p in confirmed)
    year_km      = sum(p.tour.gpx_km  or p.tour.approx_km or 0 for p in this_year_tours)
    year_ascent  = sum(p.tour.gpx_ascent or 0 for p in this_year_tours)
    tours_by_year = {}
    for p in confirmed:
        y = p.tour.tour_date.year
        if y not in tours_by_year:
            tours_by_year[y] = {'count': 0, 'km': 0, 'ascent': 0}
        tours_by_year[y]['count']  += 1
        tours_by_year[y]['km']     += p.tour.gpx_km or p.tour.approx_km or 0
        tours_by_year[y]['ascent'] += p.tour.gpx_ascent or 0
    return {
        'tour_count':    len(confirmed),
        'total_km':      round(total_km, 1),
        'total_ascent':  round(total_ascent),
        'year_count':    len(this_year_tours),
        'year_km':       round(year_km, 1),
        'year_ascent':   round(year_ascent),
        'rsvp_count':    len(all_part),
        'tours_by_year': tours_by_year,
        'this_year':     this_year,
    }


# ─── Phase 3: Profil / persönliches Logbuch ──────────────────────────────────

@app.route('/profil/<int:user_id>')
@login_required
def profil(user_id):
    user   = User.query.get_or_404(user_id)
    stats  = user_stats(user)
    badges = compute_badges(user)

    participations = (
        TourParticipant.query
        .filter_by(user_id=user_id, confirmed_present=True)
        .join(Tour)
        .order_by(Tour.tour_date.desc())
        .all()
    )
    return render_template('profil.html', member=user, stats=stats,
                           badges=badges, participations=participations)


@app.route('/profil')
@login_required
def my_profil():
    return redirect(url_for('profil', user_id=current_user.id))


# ─── Phase 3: Rangliste ───────────────────────────────────────────────────────

@app.route('/rangliste')
@login_required
def rangliste():
    from sqlalchemy.orm import joinedload
    # Alle Participations + Touren in EINEM Query laden – kein N+1
    # Nur Touren der aktiven Gruppe berücksichtigen!
    parts = (TourParticipant.query
             .filter_by(status='attending', confirmed_present=True)
             .options(joinedload(TourParticipant.tour),
                      joinedload(TourParticipant.user))
             .join(Tour)
             .filter(Tour.status == 'completed')
             .filter(Tour.id.in_(_gq(Tour).with_entities(Tour.id)))
             .all())

    # Aggregation in Python
    from collections import defaultdict
    user_km    = defaultdict(float)
    user_tours = defaultdict(int)
    user_year  = defaultdict(lambda: defaultdict(int))
    user_obj   = {}
    year       = date.today().year

    for p in parts:
        if not p.tour or not p.user:
            continue
        uid = p.user_id
        user_obj[uid] = p.user
        user_tours[uid] += 1
        if p.tour.gpx_km:
            user_km[uid] += p.tour.gpx_km
        user_year[uid][p.tour.tour_date.year if p.tour.tour_date else 0] += 1

    ranking = []
    for uid, u in user_obj.items():
        if not u.is_active:
            continue
        s = {
            'tour_count':    user_tours[uid],
            'total_km':      round(user_km[uid], 1),
            'rsvp_count':    user_tours[uid],
            'tours_by_year': dict(user_year[uid]),
        }
        ranking.append({'user': u, **s, 'badges': compute_badges(u)})

    ranking.sort(key=lambda r: (r['tour_count'], r['total_km']), reverse=True)
    annual = sorted(ranking, key=lambda r: r['tours_by_year'].get(year, 0), reverse=True)

    return render_template('rangliste.html', ranking=ranking, annual=annual,
                           year=year)


# ─── Phase 3: Jahresrückblick ─────────────────────────────────────────────────

@app.route('/touren/gpx-export')
@login_required
def gpx_export_all():
    """Alle GPX-Tracks eines Jahres als ZIP herunterladen."""
    import zipfile, io
    year = request.args.get('year', date.today().year, type=int)
    tours = _gq(Tour).filter(
        db.extract('year', Tour.tour_date) == year,
        Tour.gpx_file != None,
        Tour.status == 'completed'
    ).order_by(Tour.tour_date).all()

    if not tours:
        flash(f'Keine GPX-Tracks für {year} gefunden.', 'warning')
        return redirect(url_for('rueckblick', year=year))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for t in tours:
            src = os.path.join(app.config['UPLOAD_FOLDER_GPX'], t.gpx_file)
            if os.path.exists(src):
                dt_str = t.tour_date.strftime('%Y-%m-%d') if t.tour_date else 'offen'
                safe_title = re.sub(r'[^a-zA-Z0-9_äöüÄÖÜß-]', '_', t.title)[:40]
                zf.write(src, f'{dt_str}_{safe_title}.gpx')
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'dejungen_olen_gpx_{year}.zip'
    )


@app.route('/admin/backup/status', methods=['POST'])
@login_required
@admin_required
def admin_backup_status():
    """Backup-Status per E-Mail melden (wird vom Backup-Script aufgerufen)."""
    status  = request.form.get('status', 'unknown')
    size    = request.form.get('size', '?')
    details = request.form.get('details', '')
    send_mail(
        to=cfg('admin_email') or current_user.email,
        subject=f'{"✅" if status=="ok" else "❌"} DjO Backup {date.today().strftime("%d.%m.%Y")}',
        body=f'Backup-Status: {status}\nGröße: {size}\n\n{details}'
    )
    return jsonify({'ok': True})


@app.route('/api/docs')
@login_required
def api_docs():
    """API-Dokumentation."""
    endpoints = [
        {'method':'GET',  'path':'/api/wetter',              'desc':'Wetter für Koordinate + Datum',
         'params':'lat, lng, date (YYYY-MM-DD)'},
        {'method':'GET',  'path':'/api/location/tour/<id>',  'desc':'Live-Standorte einer Tour',
         'params':'–'},
        {'method':'POST', 'path':'/api/location/update',     'desc':'Eigenen Standort senden',
         'params':'tour_id, lat, lng, accuracy'},
        {'method':'POST', 'path':'/api/location/stop',       'desc':'Standort-Sharing beenden',
         'params':'tour_id'},
        {'method':'GET',  'path':'/touren/gpx-export',       'desc':'GPX-Tracks als ZIP',
         'params':'year (optional)'},
        {'method':'GET',  'path':'/api/suche',               'desc':'Volltextsuche',
         'params':'q (Suchbegriff)'},
    ]
    return render_template('api_docs.html', endpoints=endpoints)


@app.route('/rueckblick')
@app.route('/rueckblick/<int:year>')
@login_required
def rueckblick(year=None):
    if year is None:
        year = date.today().year

    tours = _gq(Tour).filter(
        db.extract('year', Tour.tour_date) == year,
        Tour.status == 'completed'
    ).order_by(Tour.tour_date).all()

    total_km      = sum(t.gpx_km for t in tours if t.gpx_km)
    total_ascent  = sum(t.gpx_ascent for t in tours if t.gpx_ascent)
    # Fotozählung in einer Abfrage statt N+1
    photo_counts = dict(db.session.query(
        TourPhoto.tour_id, db.func.count(TourPhoto.id)
    ).filter(TourPhoto.tour_id.in_([t.id for t in tours]))
     .group_by(TourPhoto.tour_id).all())
    total_photos = sum(photo_counts.values())

    # Participation count per user this year
    part_counts = {}
    for t in tours:
        for p in t.participants.filter_by(confirmed_present=True):
            part_counts[p.user_id] = part_counts.get(p.user_id, 0) + 1

    most_active = sorted(part_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    most_active = [(User.query.get(uid), cnt) for uid, cnt in most_active]

    # Monthly distribution
    monthly = {}
    for t in tours:
        m = t.tour_date.month
        monthly[m] = monthly.get(m, 0) + 1
    monthly_json = json.dumps([monthly.get(m, 0) for m in range(1, 13)])

    # Longest tour
    longest = max(tours, key=lambda t: t.gpx_km or 0) if tours else None

    available_years = db.session.query(
        db.extract('year', Tour.tour_date)
    ).filter(Tour.status == 'completed').distinct().order_by(
        db.extract('year', Tour.tour_date).desc()
    ).all()
    available_years = [int(r[0]) for r in available_years]

    return render_template('rueckblick.html',
                           year=year, tours=tours,
                           total_km=round(total_km,1),
                           total_ascent=int(total_ascent),
                           total_photos=total_photos,
                           most_active=most_active,
                           monthly_json=monthly_json,
                           longest=longest,
                           available_years=available_years)


# ─── Phase 4: Profil bearbeiten ───────────────────────────────────────────────

@app.route('/profil/export')
@login_required
def profil_export():
    """DSGVO-Datenexport: alle persönlichen Daten als JSON-Download."""
    u = current_user
    participations = (TourParticipant.query
                      .filter_by(user_id=u.id)
                      .options(__import__('sqlalchemy.orm', fromlist=['joinedload'])
                               .joinedload(TourParticipant.tour))
                      .all())
    photos = TourPhoto.query.filter_by(user_id=u.id).all()
    reviews = GastroReview.query.filter_by(user_id=u.id).all()

    data = {
        'export_date': datetime.utcnow().isoformat(),
        'user': {
            'id':           u.id,
            'name':         u.name,
            'email':        u.email,
            'nickname':     u.nickname,
            'bicycle_type': u.bicycle_type,
            'is_ebike':     u.is_ebike,
            'created_at':   u.created_at.isoformat() if u.created_at else None,
        },
        'touren_teilnahmen': [
            {
                'tour_id':   p.tour_id,
                'tour':      p.tour.title if p.tour else None,
                'datum':     p.tour.tour_date.isoformat() if p.tour else None,
                'status':    p.status,
                'anwesend':  p.confirmed_present,
            }
            for p in participations
        ],
        'fotos': [
            {
                'id':       ph.id,
                'tour_id':  ph.tour_id,
                'filename': ph.filename,
                'datum':    ph.taken_at.isoformat() if ph.taken_at else None,
            }
            for ph in photos
        ],
        'gastro_bewertungen': [
            {
                'spot_id': r.spot_id,
                'score':   r.score,
                'emoji':   r.emoji,
                'datum':   r.created_at.isoformat() if r.created_at else None,
            }
            for r in reviews
        ],
    }

    import json as _json
    response = make_response(_json.dumps(data, ensure_ascii=False, indent=2))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    response.headers['Content-Disposition'] = (
        f'attachment; filename="djo_export_{u.id}_{date.today()}.json"'
    )
    return response


@app.route('/profil/bearbeiten', methods=['GET', 'POST'])
@login_required
def profil_edit():
    if request.method == 'POST':
        current_user.name        = request.form.get('name','').strip() or current_user.name
        current_user.nickname    = request.form.get('nickname','').strip() or None
        current_user.bicycle_type = request.form.get('bicycle_type', current_user.bicycle_type)
        current_user.is_ebike    = bool(request.form.get('is_ebike'))
        current_user.bio         = request.form.get('bio','').strip() or None
        bday = request.form.get('birthday','').strip()
        if bday:
            try:
                current_user.birthday = datetime.strptime(bday, '%Y-%m-%d').date()
            except ValueError:
                pass
        else:
            current_user.birthday = None

        # Password change (optional)
        pw = request.form.get('password','').strip()
        if pw:
            pw2 = request.form.get('password2','').strip()
            if pw == pw2 and len(pw) >= 8:
                current_user.set_password(pw)
                flash('Passwort geändert.', 'info')
            else:
                flash('Passwörter stimmen nicht überein oder zu kurz.', 'warning')

        db.session.commit()
        flash('Profil gespeichert!', 'success')
        return redirect(url_for('my_profil'))
    return render_template('profil_edit.html')


# ─── Photo management: delete, edit GPS, manual GPS set ─────────────────────

def _can_edit_photo(photo, tour=None):
    """Nur Uploader, Tour-Ersteller, Organizer oder Admin dürfen Fotos bearbeiten/löschen."""
    if current_user.is_admin or current_user.is_organizer:
        return True
    if photo.user_id == current_user.id:
        return True
    if tour and tour.created_by == current_user.id:
        return True
    return False


@app.route('/fotos/<int:photo_id>/loeschen', methods=['POST'])
@login_required
def photo_delete(photo_id):
    photo = TourPhoto.query.get_or_404(photo_id)
    tour  = Tour.query.get(photo.tour_id)
    if not _can_edit_photo(photo, tour):
        abort(403)
    tour_id = photo.tour_id
    try:
        path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photo.filename)
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        app.logger.warning(f'Could not delete photo file: {e}')
    db.session.delete(photo)
    db.session.commit()
    flash('Foto gelöscht.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#fotos')


@app.route('/fotos/<int:photo_id>/nach-vorne', methods=['POST'])
@login_required
def photo_move_front(photo_id):
    photo = TourPhoto.query.get_or_404(photo_id)
    tour  = Tour.query.get_or_404(photo.tour_id)
    if (tour.created_by != current_user.id
            and photo.user_id != current_user.id
            and not current_user.is_admin):
        abort(403)
    others = TourPhoto.query.filter(
        TourPhoto.tour_id == photo.tour_id,
        TourPhoto.id != photo.id
    ).order_by(
        db.text('COALESCE(sort_order, 999999) ASC'),
        TourPhoto.taken_at.asc().nullslast(),
        TourPhoto.created_at.asc()
    ).all()
    for i, p in enumerate(others, start=1):
        p.sort_order = i
    photo.sort_order = 0
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/touren/<int:tour_id>/fotos/reihenfolge', methods=['POST'])
@login_required
def photo_reorder(tour_id):
    """Speichert neue Foto-Reihenfolge per Drag & Drop."""
    tour = Tour.query.get_or_404(tour_id)
    if tour.created_by != current_user.id and not current_user.is_admin:
        abort(403)
    data = request.get_json() or {}
    ids  = data.get('order', [])
    if not ids:
        return jsonify({'ok': False, 'error': 'Keine IDs erhalten'})
    try:
        from sqlalchemy import text
        for i, pid in enumerate(ids):
            db.session.execute(
                text('UPDATE tour_photos SET sort_order=:so WHERE id=:id AND tour_id=:tid'),
                {'so': i, 'id': int(pid), 'tid': tour_id}
            )
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'photo_reorder error: {e}')
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/fotos/<int:photo_id>/gps', methods=['POST'])
@login_required
def photo_set_gps(photo_id):
    """Manually set or correct GPS for a photo."""
    photo = TourPhoto.query.get_or_404(photo_id)
    tour  = Tour.query.get(photo.tour_id)
    if not _can_edit_photo(photo, tour):
        abort(403)
    try:
        lat = float(request.form.get('lat', ''))
        lng = float(request.form.get('lng', ''))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            photo.lat = round(lat, 6)
            photo.lng = round(lng, 6)
            db.session.commit()
            flash('GPS-Position gespeichert.', 'success')
        else:
            flash('Ungültige Koordinaten.', 'danger')
    except (ValueError, TypeError):
        flash('Bitte gültige Koordinaten eingeben.', 'danger')
    return redirect(url_for('tour_detail', tour_id=photo.tour_id) + '#fotos')


@app.route('/fotos/<int:photo_id>/gps-loeschen', methods=['POST'])
@login_required
def photo_clear_gps(photo_id):
    """Remove GPS coords from a photo."""
    photo = TourPhoto.query.get_or_404(photo_id)
    tour  = Tour.query.get(photo.tour_id)
    if not _can_edit_photo(photo, tour):
        abort(403)
    photo.lat = None
    photo.lng = None
    db.session.commit()
    flash('GPS-Daten entfernt.', 'success')
    return redirect(url_for('tour_detail', tour_id=photo.tour_id) + '#fotos')



# ─── Avatar upload ────────────────────────────────────────────────────────────

@app.route('/profil/avatar', methods=['POST'])
@login_required
def avatar_upload():
    f = request.files.get('avatar')
    if not f or not allowed_file(f.filename, {'jpg','jpeg','png','webp','gif'}):
        flash('Bitte ein gültiges Bild hochladen (JPG/PNG/WEBP).', 'danger')
        return redirect(url_for('profil_edit'))

    os.makedirs(app.config['UPLOAD_FOLDER_AVATARS'], exist_ok=True)
    # Remove old avatar
    if current_user.avatar:
        old = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], current_user.avatar)
        if os.path.exists(old):
            os.remove(old)

    ext      = f.filename.rsplit('.', 1)[1].lower()
    filename = f'avatar_{current_user.id}_{secrets.token_hex(4)}.{ext}'
    path     = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], filename)

    # Resize to max 256×256 to save space
    try:
        from PIL import Image as PILImage
        img = PILImage.open(f)
        img.thumbnail((256, 256))
        img.save(path, optimize=True)
    except Exception:
        f.seek(0)
        f.save(path)

    current_user.avatar = filename
    db.session.commit()
    flash('Profilbild gespeichert!', 'success')
    return redirect(url_for('profil_edit'))


@app.route('/profil/avatar/loeschen', methods=['POST'])
@login_required
def avatar_delete():
    if current_user.avatar:
        path = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], current_user.avatar)
        if os.path.exists(path):
            os.remove(path)
        current_user.avatar = None
        db.session.commit()
        flash('Profilbild entfernt.', 'success')
    return redirect(url_for('profil_edit'))


# ─── Admin: Site settings ─────────────────────────────────────────────────────

@app.route('/admin/einstellungen', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_settings():
    mail_configured = bool(os.getenv('MAIL_SERVER', ''))
    if request.method == 'POST':
        keys = [
            'telegram_bot_token', 'telegram_chat_id', 'telegram_chat_username',
            'telegram_invite_link',
            'default_start_time', 'default_meeting_desc',
            'default_meeting_lat', 'default_meeting_lng',
            'morning_opener_until', 'site_name', 'base_url',
            'google_places_api_key',
        ]
        for key in keys:
            val = request.form.get(key, '').strip()
            SiteConfig.set(key, val)
        flash('Einstellungen gespeichert!', 'success')
        return redirect(url_for('admin_settings'))

    settings = {k: cfg(k) for k in SiteConfig.DEFAULTS}
    return render_template('admin/settings.html', mail_configured=mail_configured, settings=settings)


@app.route('/admin/telegram-test', methods=['POST'])
@login_required
@admin_required
def admin_telegram_test():
    """Send a test message – show exact Telegram API response for debugging."""
    token   = cfg('telegram_bot_token').strip()
    chat_id = cfg('telegram_chat_id').strip()

    if not token:
        flash('❌ Bot-Token ist leer. Bitte in Einstellungen speichern.', 'danger')
        return redirect(url_for('admin_settings'))
    if not chat_id:
        flash('❌ Chat-ID ist leer. Bitte in Einstellungen speichern.', 'danger')
        return redirect(url_for('admin_settings'))

    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': '✅ Verbindungstest – De jungen Olen\n\nDer Telegram-Bot ist erfolgreich konfiguriert!',
        'parse_mode': 'HTML'
    }

    # Try requests first, fall back to urllib
    status_code = None
    response_text = ''
    try:
        r = http_requests.post(url, json=payload, timeout=10)
        status_code   = r.status_code
        response_text = r.text
    except Exception as req_err:
        # Fallback: urllib (always available, no extra package needed)
        try:
            import urllib.request, urllib.parse, json as _json
            data = _json.dumps(payload).encode('utf-8')
            req  = urllib.request.Request(url, data=data,
                                          headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code   = resp.status
                response_text = resp.read().decode('utf-8')
        except Exception as url_err:
            flash(f'❌ Netzwerkfehler: {url_err} | requests-Fehler: {req_err}', 'danger')
            return redirect(url_for('admin_settings'))

    if status_code == 200:
        flash('✅ Test-Nachricht gesendet! Bot funktioniert.', 'success')
    else:
        # Parse Telegram error
        try:
            import json as _json
            resp_json = _json.loads(response_text)
            tg_desc   = resp_json.get('description', response_text)
        except Exception:
            tg_desc = response_text[:200]
        flash(
            f'❌ Telegram-Fehler (HTTP {status_code}): {tg_desc}  |  '
            f'Token endet auf: ...{token[-6:]}  |  Chat-ID: {chat_id}',
            'danger'
        )
    return redirect(url_for('admin_settings'))


@app.route('/admin/benutzer/<int:user_id>/email', methods=['POST'])
@login_required
@admin_required
def admin_change_email(user_id):
    user = User.query.get_or_404(user_id)
    new_email = request.form.get('email','').strip().lower()
    if not new_email:
        flash('E-Mail darf nicht leer sein.', 'danger')
        return redirect(url_for('admin_dashboard'))
    if User.query.filter_by(email=new_email).first():
        flash('Diese E-Mail ist bereits vergeben.', 'danger')
        return redirect(url_for('admin_dashboard'))
    user.email = new_email
    db.session.commit()
    flash(f'E-Mail von {user.name} geändert.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/benutzer/<int:user_id>/passwort', methods=['POST'])
@login_required
@admin_required
def admin_reset_pw(user_id):
    user = User.query.get_or_404(user_id)
    pw   = request.form.get('password','').strip()
    if len(pw) < 6:
        flash('Passwort muss mindestens 6 Zeichen haben.', 'danger')
        return redirect(url_for('admin_dashboard'))
    user.set_password(pw)
    db.session.commit()
    flash(f'Passwort für {user.name} zurückgesetzt.', 'success')
    return redirect(url_for('admin_dashboard'))


# ─── API: re-extract GPS from existing photo ─────────────────────────────────

@app.route('/api/fotos/<int:photo_id>/reextract-gps')
@login_required
def api_reextract_gps(photo_id):
    """Re-run EXIF extraction on a saved photo. Returns JSON."""
    photo = TourPhoto.query.get_or_404(photo_id)
    if photo.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photo.filename)
    lat, lng = extract_gps_from_exif(path)
    if lat and lng:
        photo.lat = lat
        photo.lng = lng
        db.session.commit()
        return jsonify({'ok': True, 'lat': lat, 'lng': lng})
    return jsonify({'ok': False, 'msg': 'Keine GPS-Daten in EXIF gefunden'})


# ─── GPS-Diagnose ─────────────────────────────────────────────────────────────

@app.route('/admin/gps-diagnose', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_gps_diagnose():
    result = None
    if request.method == 'POST':
        f = request.files.get('photo')
        if f:
            import tempfile, traceback
            suffix = '.' + f.filename.rsplit('.',1)[-1].lower()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                f.save(tmp.name)
                path = tmp.name

            lines = []

            # 1. piexif
            try:
                import piexif
                exif = piexif.load(path)
                gps  = exif.get('GPS', {})
                lines.append(f'✅ piexif installiert. GPS keys: {list(gps.keys())}')
                lines.append(f'   GPS raw: {gps}')
                if gps:
                    import piexif as px
                    def rat(v):
                        return v[0]/v[1] if isinstance(v,tuple) and v[1] else float(v)
                    def dms(seq,ref):
                        d=rat(seq[0]);m=rat(seq[1]);s=rat(seq[2])
                        dec=d+m/60+s/3600
                        ref=ref.decode() if isinstance(ref,bytes) else ref
                        if ref in('S','W'):dec=-dec
                        return round(dec,6)
                    if px.GPSIFD.GPSLatitude in gps:
                        lat=dms(gps[px.GPSIFD.GPSLatitude], gps.get(px.GPSIFD.GPSLatitudeRef,b'N'))
                        lng=dms(gps[px.GPSIFD.GPSLongitude],gps.get(px.GPSIFD.GPSLongitudeRef,b'E'))
                        lines.append(f'✅ piexif GPS: lat={lat}, lng={lng}')
                    else:
                        lines.append('⚠️ piexif: kein GPSLatitude key in GPS-IFD')
                else:
                    lines.append('⚠️ piexif: GPS-Block ist leer')
            except ImportError:
                lines.append('❌ piexif nicht installiert! → In Plesk installieren: piexif')
            except Exception as e:
                lines.append(f'❌ piexif Fehler: {e}')
                lines.append(traceback.format_exc())

            # 2. Pillow
            try:
                from PIL import Image, ExifTags
                from PIL.ExifTags import TAGS, GPSTAGS
                img = Image.open(path)
                lines.append(f'✅ Pillow OK, Pillow-Version: {Image.__version__}')
                exif_obj = img.getexif()
                lines.append(f'   getexif() tags: {len(exif_obj)}')
                gps_tag = next((k for k,v in TAGS.items() if v=='GPSInfo'),None)
                lines.append(f'   GPSInfo tag ID: {gps_tag}, present: {gps_tag in exif_obj}')
                if gps_tag and gps_tag in exif_obj:
                    try:
                        ifd = exif_obj.get_ifd(gps_tag)
                        lines.append(f'   get_ifd() result: {dict(ifd)}')
                    except Exception as e2:
                        lines.append(f'   get_ifd() Fehler: {e2}')
                # legacy
                try:
                    leg = img._getexif()
                    if leg:
                        for tid,val in leg.items():
                            if TAGS.get(tid)=='GPSInfo':
                                lines.append(f'   _getexif() GPS: {val}')
                except Exception as e3:
                    lines.append(f'   _getexif() Fehler: {e3}')
            except Exception as e:
                lines.append(f'❌ Pillow Fehler: {e}')

            # 3. Full extraction
            try:
                lat, lng = extract_gps_from_exif(path)
                lines.append(f'\n→ extract_gps_from_exif(): lat={lat}, lng={lng}')
            except Exception as e:
                lines.append(f'\n→ extract_gps_from_exif() Exception: {e}')
                lines.append(traceback.format_exc())

            os.remove(path)
            result = '\n'.join(lines)

    return render_template('admin/gps_diagnose.html', result=result)


# ─── SiteConfig: initialize defaults on first run ─────────────────────────────
def init_site_config():
    """Set default SiteConfig values if not yet in DB."""
    try:
        for key, value in SiteConfig.DEFAULTS.items():
            if SiteConfig.get(key) is None:
                db.session.add(SiteConfig(key=key, value=value))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f'SiteConfig init error: {e}')



def enable_wal():
    """SQLite WAL-Modus aktivieren."""
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text('PRAGMA journal_mode=WAL'))
            conn.execute(text('PRAGMA synchronous=NORMAL'))
            conn.execute(text('PRAGMA cache_size=-64000'))
            conn.commit()
    except Exception as e:
        app.logger.warning(f'WAL mode not set: {e}')


# ── Proposal-Stub-Routen (Feature entfernt) ──────────────────────────────────
@app.route('/proposals/new', methods=['GET','POST'])
@login_required
def proposal_new():
    flash('Das Vorschläge-Feature wurde entfernt. Touren direkt unter „Neue Tour" erstellen.', 'info')
    return redirect(url_for('tour_list'))

@app.route('/proposals/<int:prop_id>', methods=['GET'])
@app.route('/proposals/<int:prop_id>/edit', methods=['GET','POST'])
@login_required
def proposal_edit(prop_id):
    flash('Das Vorschläge-Feature wurde entfernt.', 'info')
    return redirect(url_for('tour_list'))

@app.route('/proposals/<int:prop_id>/delete', methods=['POST'])
@login_required
def proposal_delete(prop_id):
    return redirect(url_for('tour_list'))

@app.route('/proposals/<int:prop_id>/to-tour', methods=['POST'])
@login_required
def proposal_to_tour(prop_id):
    return redirect(url_for('tour_list'))

@app.route('/proposals/<int:prop_id>/vote', methods=['POST'])
@login_required
def proposal_vote(prop_id):
    return redirect(url_for('tour_list'))

@app.route('/proposals/<int:prop_id>/add-dates', methods=['GET','POST'])
@login_required
def proposal_add_dates(prop_id):
    return redirect(url_for('tour_list'))

@app.route('/proposals/<int:prop_id>/gpx')
@login_required
def proposal_gpx_download(prop_id):
    return redirect(url_for('tour_list'))

@app.route('/proposals/dates/<int:option_id>/confirm', methods=['POST'])
@login_required
def proposal_confirm_date(option_id):
    return redirect(url_for('tour_list'))

@app.route('/proposals/<int:prop_id>/list')
@login_required
def proposal_list(prop_id=None):
    return redirect(url_for('tour_list'))


@app.route('/gruppe/wechseln/<int:group_id>', methods=['POST'])
@login_required
def switch_group(group_id):
    """Aktive Gruppe wechseln (nur für Admins mit Zugang zu mehreren Gruppen)."""
    from flask import session as _sess
    group = Group.query.get_or_404(group_id)
    # Nur wenn User dieser Gruppe angehört ODER Super-Admin (group_id=None)
    if current_user.group_id == group_id or current_user.role == 'admin':
        _sess['active_group_id'] = group_id
        flash(f'Gruppe gewechselt zu: {group.name}', 'success')
    else:
        flash('Kein Zugang zu dieser Gruppe.', 'danger')
    return redirect(request.referrer or url_for('index'))


@app.route('/gruppe/neu', methods=['GET', 'POST'])
@login_required
def group_create():
    """Neue Gruppe anlegen (nur Super-Admin: role=admin ohne group_id)."""
    if not (current_user.role == 'admin'):
        abort(403)
    if request.method == 'POST':
        slug = re.sub(r'[^a-z0-9-]', '-', request.form.get('slug', '').lower().strip())[:40]
        name = request.form.get('name', '').strip()
        if not slug or not name:
            flash('Slug und Name sind erforderlich.', 'danger')
        elif Group.query.filter_by(slug=slug).first():
            flash(f'Slug „{slug}" ist bereits vergeben.', 'danger')
        else:
            group = Group(slug=slug, name=name,
                          description=request.form.get('description','').strip() or None)
            db.session.add(group)
            db.session.flush()  # group.id verfügbar machen, ohne schon zu committen

            # Logo-Upload (optional)
            logo_file = request.files.get('logo')
            if logo_file and logo_file.filename:
                ext = logo_file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'webp'):
                    logo_dir = os.path.join(app.root_path, 'static', 'uploads', 'group_logos')
                    os.makedirs(logo_dir, exist_ok=True)
                    logo_fname = f'group_{group.id}_{secrets.token_hex(6)}.{ext}'
                    logo_path  = os.path.join(logo_dir, logo_fname)
                    logo_file.save(logo_path)
                    try:
                        _resize_photo_if_needed(logo_path, max_px=400)
                    except Exception:
                        pass
                    group.logo = logo_fname
                else:
                    flash('Logo: nur PNG, JPG oder WEBP erlaubt – Gruppe wurde ohne Logo erstellt.', 'warning')

            db.session.commit()
            flash(f'Gruppe „{name}" erstellt! Jetzt Mitglieder einladen.', 'success')
            from flask import session as _sess
            _sess['active_group_id'] = group.id
            return redirect(url_for('admin_dashboard'))
    return render_template('gruppe_neu.html')


@app.route('/gruppe/<int:group_id>/logo', methods=['POST'])
@login_required
def group_logo_upload(group_id):
    """Logo einer bestehenden Gruppe ändern (nur Super-Admin)."""
    if current_user.role != 'admin':
        abort(403)
    group = Group.query.get_or_404(group_id)
    logo_file = request.files.get('logo')
    if not logo_file or not logo_file.filename:
        flash('Keine Datei ausgewählt.', 'warning')
        return redirect(url_for('admin_groups'))
    ext = logo_file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('png', 'jpg', 'jpeg', 'webp'):
        flash('Nur PNG, JPG oder WEBP erlaubt.', 'danger')
        return redirect(url_for('admin_groups'))

    logo_dir = os.path.join(app.root_path, 'static', 'uploads', 'group_logos')
    os.makedirs(logo_dir, exist_ok=True)

    # Altes Logo löschen
    if group.logo:
        old_path = os.path.join(logo_dir, group.logo)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass

    logo_fname = f'group_{group.id}_{secrets.token_hex(6)}.{ext}'
    logo_path  = os.path.join(logo_dir, logo_fname)
    logo_file.save(logo_path)
    try:
        _resize_photo_if_needed(logo_path, max_px=400)
    except Exception:
        pass
    group.logo = logo_fname
    db.session.commit()
    flash(f'Logo für „{group.name}" aktualisiert.', 'success')
    return redirect(url_for('admin_groups'))


@app.route('/admin/gruppen')
@login_required
def admin_groups():
    """Übersicht aller Gruppen (nur Super-Admin)."""
    if current_user.role != 'admin':
        abort(403)
    groups = Group.query.order_by(Group.created_at).all()
    return render_template('admin/gruppen.html', groups=groups)


@app.route('/admin/gruppen/<int:group_id>/loeschen', methods=['POST'])
@login_required
def group_delete(group_id):
    """Gruppe löschen (nur Super-Admin). Nur möglich wenn keine Mitglieder/Touren zugeordnet sind,
    es sei denn ?force=1 wird mitgesendet – dann werden alle zugehörigen Daten mitgelöscht."""
    if current_user.role != 'admin':
        abort(403)
    group = Group.query.get_or_404(group_id)

    member_count = group.users.count()
    tour_count   = group.tours.count()
    force = request.form.get('force') == '1'

    if (member_count > 0 or tour_count > 0) and not force:
        flash(f'Gruppe „{group.name}" hat noch {member_count} Mitglied(er) und '
              f'{tour_count} Tour(en). Zum endgültigen Löschen inkl. aller Daten '
              f'bitte „Endgültig löschen" verwenden.', 'danger')
        return redirect(url_for('admin_groups'))

    try:
        if force:
            # Alle Touren der Gruppe löschen (inkl. Fotos/Videos/GPX von der Platte)
            for tour in group.tours.all():
                for p in TourPhoto.query.filter_by(tour_id=tour.id).all():
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], p.filename))
                    except Exception:
                        pass
                video_dir = app.config.get('UPLOAD_FOLDER_VIDEOS',
                            os.path.join(app.root_path, 'static', 'uploads', 'videos'))
                for v in TourVideo.query.filter_by(tour_id=tour.id).all():
                    try:
                        os.remove(os.path.join(video_dir, v.filename))
                    except Exception:
                        pass
                if tour.gpx_file:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file))
                    except Exception:
                        pass
                db.session.delete(tour)
            # Alle Mitglieder der Gruppe löschen (außer dem aktuell eingeloggten Super-Admin)
            for user in group.users.all():
                if user.id != current_user.id:
                    db.session.delete(user)
                else:
                    user.group_id = None  # sich selbst nicht löschen, nur aus Gruppe entfernen
            # Offene Einladungen der Gruppe löschen
            for inv in group.invites.all():
                db.session.delete(inv)

        name = group.name
        db.session.delete(group)
        db.session.commit()

        # Falls die gelöschte Gruppe die aktive war: Session zurücksetzen
        from flask import session as _sess
        if _sess.get('active_group_id') == group_id:
            _sess.pop('active_group_id', None)

        flash(f'Gruppe „{name}" wurde gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Löschen: {e}', 'danger')

    return redirect(url_for('admin_groups'))


@app.route('/admin/run-migration', methods=['GET', 'POST'])
def run_migration_now():
    """Einmalige Route um migrate_db() manuell auszuführen.
    WICHTIG: Nach Ausführung wieder entfernen oder absichern!
    """
    # Simple security: require a secret token
    token = request.args.get('token', '')
    expected = app.config.get('SECRET_KEY', '')[:16]
    if token != expected:
        return 'Bitte token= Parameter angeben (erste 16 Zeichen des SECRET_KEY)', 403

    try:
        migrate_db()
        return '<h2>✅ Migration erfolgreich!</h2><p>Bitte Seite neu laden und diese URL danach nicht mehr aufrufen.</p>', 200
    except Exception as e:
        import traceback
        return f'<h2>❌ Fehler:</h2><pre>{traceback.format_exc()}</pre>', 500


def migrate_db():
    """Add missing columns to existing tables without losing data."""
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)

    def column_exists(table, col):
        try:
            cols = [c['name'] for c in inspector.get_columns(table)]
            return col in cols
        except Exception:
            return False

    def add_column(table, col, col_type):
        if not column_exists(table, col):
            try:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
                    conn.commit()
                app.logger.info(f'Migration: added {table}.{col}')
                # Refresh inspector cache
                inspector = inspect(db.engine)
            except Exception as e:
                app.logger.warning(f'Migration skip {table}.{col}: {e}')

    # users table – new columns added over time
    add_column('users', 'last_login', 'DATETIME')

    # Push Subscriptions
    try:
        with db.engine.connect() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS live_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tour_id INTEGER NOT NULL REFERENCES tours(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                lat REAL NOT NULL, lng REAL NOT NULL,
                accuracy REAL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tour_id, user_id)
            )'''))
            conn.commit()
    except Exception as e:
        app.logger.debug(f'push/live tables: {e}')
    # ── Nutzer-Spalten ───────────────────────────────────────────────────────
    add_column('users', 'birthday',  'DATE')

    # ── Multi-Tenancy: Gruppen ────────────────────────────────────────────────
    # groups-Tabelle
    try:
        conn.execute(text('''CREATE TABLE IF NOT EXISTS groups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            logo        TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active   INTEGER DEFAULT 1
        )'''))
        # Bestehende Installation: Standard-Gruppe aus SiteConfig erstellen
        row = conn.execute(text("SELECT value FROM site_config WHERE key='group_name'")).fetchone()
        group_name = row[0] if row else 'De jungen Olen'
        exists = conn.execute(text("SELECT id FROM groups LIMIT 1")).fetchone()
        if not exists:
            conn.execute(text(
                "INSERT INTO groups (slug, name) VALUES (:slug, :name)"
            ), {'slug': 'default', 'name': group_name})
        conn.commit()
    except Exception as e:
        app.logger.info(f'groups table: {e}')

    # group_id Spalten
    default_gid = conn.execute(text("SELECT id FROM groups LIMIT 1")).fetchone()
    if default_gid:
        default_gid = default_gid[0]
        add_column('users',        'group_id', f'INTEGER DEFAULT {default_gid}')
        add_column('tours',        'group_id', f'INTEGER DEFAULT {default_gid}')
        add_column('invite_tokens','group_id', f'INTEGER DEFAULT {default_gid}')
        # Bestehende Zeilen zuordnen
        for table in ('users', 'tours', 'invite_tokens'):
            try:
                conn.execute(text(f"UPDATE {table} SET group_id={default_gid} WHERE group_id IS NULL"))
                conn.commit()
            except Exception:
                pass
    add_column('users', 'bio',       'VARCHAR(300)')
    add_column('users', 'avatar',    'VARCHAR(200)')

    # tours table
    add_column('tours', 'gpx_km',       'FLOAT')
    add_column('tours', 'gpx_ascent',   'FLOAT')
    add_column('tours', 'meeting_lat',  'FLOAT')
    add_column('tours', 'meeting_lng',  'FLOAT')
    add_column('tours', 'meeting_desc', 'VARCHAR(200)')

    # tour_participants table
    # time_votes Tabelle
    try:
        with db.engine.connect() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS time_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tour_id INTEGER NOT NULL REFERENCES tours(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                time_slot VARCHAR(5) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tour_id, user_id, time_slot)
            )'''))
            conn.commit()
    except Exception as e:
        app.logger.debug(f'time_votes: {e}')

    # ── Teilnehmer/Fotos/Sonstiges ──────────────────────────────────────────
    add_column('tour_participants', 'confirmed_present', 'BOOLEAN DEFAULT 0')

    add_column('tour_photos', 'taken_at',   'DATETIME')
    add_column('tour_photos', 'sort_order', 'INTEGER')
    add_column('users', 'morning_opener_until', 'VARCHAR(5)')
    add_column('tours', 'approx_km',      'FLOAT')
    add_column('tours', 'external_link',  'VARCHAR(500)')
    add_column('invite_tokens', 'label',  'VARCHAR(100)')

    # gastro_photos Tabelle
    try:
        with db.engine.connect() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS gastro_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id INTEGER NOT NULL REFERENCES gastro_spots(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                filename VARCHAR(200) NOT NULL,
                caption VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )'''))
            conn.commit()
    except Exception as e:
        app.logger.debug(f'gastro_photos: {e}')

    # tour_videos Tabelle
    try:
        with db.engine.connect() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS tour_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tour_id INTEGER NOT NULL REFERENCES tours(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                filename VARCHAR(200) NOT NULL,
                title VARCHAR(200),
                filesize INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )'''))
            conn.commit()
    except Exception as e:
        app.logger.debug(f'tour_videos table: {e}')

    # tour_date: NULL erlauben (Datum noch offen)
    try:
        with db.engine.connect() as conn:
            # SQLite erlaubt keine ALTER COLUMN – neue Tabelle mit nullable tour_date
            # wird via db.create_all() mit dem aktualisierten Model angelegt
            # Bestehende Daten bleiben erhalten
            conn.execute(text('SELECT 1'))
    except Exception:
        pass

    # RouteRating Tabelle
    try:
        with db.engine.connect() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS route_ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tour_id INTEGER NOT NULL REFERENCES tours(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                rating VARCHAR(10) NOT NULL,
                comment VARCHAR(300),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tour_id, user_id)
            )'''))
            conn.commit()
    except Exception as e:
        app.logger.debug(f'route_ratings table: {e}')

    # Datenbank-Indizes für häufige FK-Abfragen
    def add_index(table, col):
        try:
            with db.engine.connect() as conn:
                idx_name = f'ix_{table}_{col}'
                conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col})'
                ))
                conn.commit()
        except Exception:
            pass

    add_index('tours',             'created_by')
    add_index('tours',             'status')
    add_index('tour_participants', 'tour_id')
    add_index('tour_participants', 'user_id')
    add_index('tour_photos',       'tour_id')
    add_index('tour_photos',       'user_id')
    add_index('tour_comments',     'tour_id')
    add_index('tour_comments',     'user_id')
    add_index('gastro_spots',      'spot_type')
    add_index('gastro_reviews',    'spot_id')
    add_index('gastro_reviews',    'user_id')



    add_column('gastro_spots', 'osm_id',   'VARCHAR(30)')
    add_column('gastro_spots', 'website',  'VARCHAR(200)')
    add_column('gastro_spots', 'phone',    'VARCHAR(30)')


# ─── Archiv-Suche ─────────────────────────────────────────────────────────────


@app.before_request
def load_group_context():
    """Bestimmt die aktive Gruppe für den aktuellen User und setzt g.group.
    Läuft vor jedem Request, damit current_group in Templates verfügbar ist."""
    from flask import g as _g
    _g.group = None

    if current_user.is_authenticated:
        from flask import session as _sess
        gid = _sess.get('active_group_id') or getattr(current_user, 'group_id', None)
        if gid:
            _g.group = Group.query.get(gid)
        if not _g.group and current_user.group_id:
            _g.group = Group.query.get(current_user.group_id)
        if not _g.group:
            _g.group = Group.query.filter_by(is_active=True).first()


# ── Auto-migrate: runs once on first request ────────────────────────────────
@app.before_request
def _auto_migrate_once():
    global _db_migrated
    if not _db_migrated:
        try:
            db.create_all()
            migrate_db()
            init_site_config()
        except Exception as e:
            app.logger.warning(f'Auto-migrate error: {e}')
        _db_migrated = True

@app.route('/archiv/suche')
@login_required
def archiv_suche():
    q      = request.args.get('q','').strip()
    year   = request.args.get('year','')
    diff   = request.args.get('diff','')

    tours = _gq(Tour).filter_by(status='completed')
    if q:
        tours = tours.filter(Tour.title.ilike(f'%{q}%'))
    if year:
        tours = tours.filter(db.extract('year', Tour.tour_date) == int(year))
    if diff:
        tours = tours.filter_by(difficulty=diff)
    tours = tours.order_by(Tour.tour_date.desc()).all()

    all_years = db.session.query(
        db.extract('year', Tour.tour_date)
    ).filter(Tour.status == 'completed').distinct().order_by(
        db.extract('year', Tour.tour_date).desc()
    ).all()
    all_years = [int(r[0]) for r in all_years]

    return render_template('touren/archiv.html', tours=tours,
                           q=q, year=year, diff=diff, all_years=all_years,
                           is_search=True)


# ─── Gruppen-Meilensteine ─────────────────────────────────────────────────────

def group_milestones():
    """Return achieved and next group milestones for the ACTIVE group. Safe for empty DB."""
    try:
        base = _gq(Tour).filter_by(status='completed')
        total_km = db.session.query(
            db.func.sum(Tour.gpx_km)
        ).filter(Tour.id.in_(base.with_entities(Tour.id))).scalar() or 0
        total_tours = base.count()
    except Exception:
        total_km, total_tours = 0, 0

    km_milestones  = [100, 250, 500, 1000, 2500, 5000, 10000]
    tou_milestones = [10, 25, 50, 100, 200, 500]

    achieved_km  = [m for m in km_milestones  if total_km    >= m]
    achieved_tou = [m for m in tou_milestones if total_tours >= m]
    next_km  = next((m for m in km_milestones  if total_km    < m), None)
    next_tou = next((m for m in tou_milestones if total_tours < m), None)

    return {
        'total_km':    round(float(total_km), 1),
        'total_tours': total_tours,
        'achieved_km':  achieved_km,
        'achieved_tou': achieved_tou,
        'next_km':  next_km,
        'next_tou': next_tou,
        'pct_km':   min(99, round(float(total_km)  / next_km  * 100)) if next_km  else 100,
        'pct_tou':  min(99, round(total_tours / next_tou * 100)) if next_tou else 100,
    }


# ─── DSGVO / Datenschutz ──────────────────────────────────────────────────────

@app.route('/datenschutz')
def datenschutz():
    return render_template('datenschutz.html',
                           site_name=cfg('site_name') or 'De jungen Olen')


@app.route('/datenschutz/loeschen', methods=['POST'])
@login_required
def datenschutz_delete_account():
    """GDPR: user deletes own account and all personal data."""
    user = current_user
    # Delete avatar
    if user.avatar:
        path = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], user.avatar)
        if os.path.exists(path):
            os.remove(path)
    # Anonymize instead of hard-delete (keep tour participation count intact)
    user.name         = f'Gelöschter Nutzer {user.id}'
    user.nickname     = None
    user.email        = f'deleted_{user.id}@deleted.local'
    user.password_hash = secrets.token_hex(32)
    user.is_active    = False
    user.avatar       = None
    user.bio          = None
    user.birthday     = None
    db.session.commit()
    logout_user()
    flash('Dein Konto und deine persönlichen Daten wurden gelöscht.', 'success')
    return redirect(url_for('login'))


# ─── Monthly newsletter export (PDF-ready HTML) ───────────────────────────────

@app.route('/newsletter/<int:year>/<int:month>')
@login_required
def newsletter(year, month):
    from calendar import month_name as cal_month
    import locale
    tours = _gq(Tour).filter(
        Tour.status == 'completed',
        db.extract('year',  Tour.tour_date) == year,
        db.extract('month', Tour.tour_date) == month,
    ).order_by(Tour.tour_date).all()

    upcoming = _gq(Tour).filter(
        Tour.status == 'planned',
        Tour.tour_date >= date.today()
    ).order_by(Tour.tour_date).limit(5).all()

    milestones = group_milestones()
    month_label = f'{month:02d}/{year}'

    total_km = sum(t.gpx_km for t in tours if t.gpx_km)
    return render_template('newsletter.html',
                           tours=tours, upcoming=upcoming,
                           milestones=milestones,
                           year=year, month=month,
                           month_label=month_label,
                           total_km=round(total_km, 1))


@app.route('/newsletter')
@login_required
def newsletter_current():
    today = date.today()
    # Previous month
    m = today.month - 1 or 12
    y = today.year if today.month > 1 else today.year - 1
    return redirect(url_for('newsletter', year=y, month=m))


# ─── Admin: export data ────────────────────────────────────────────────────────

@app.route('/admin/export/mitglieder')
@login_required
@admin_required
def admin_export_members():
    """CSV export of all members."""
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['ID','Name','Spitzname','E-Mail','Rolle','Fahrrad','E-Bike',
                     'Geburtstag','Touren','erstellt'])
    users = _gq(User).order_by(User.name).all()
    for u in users:
        confirmed = TourParticipant.query.filter_by(user_id=u.id, confirmed_present=True).count()
        writer.writerow([
            u.id, u.name, u.nickname or '', u.email, u.role,
            u.bicycle_type, '1' if u.is_ebike else '0',
            u.birthday.isoformat() if u.birthday else '',
            confirmed,
            u.created_at.strftime('%Y-%m-%d')
        ])
    from flask import Response
    return Response(
        '\ufeff' + output.getvalue(),  # BOM for Excel
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': 'attachment; filename="mitglieder.csv"'}
    )


@app.route('/admin/export/touren')
@login_required
@admin_required
def admin_export_tours():
    """CSV export of all tours."""
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['ID','Titel','Datum','Status','Schwierigkeit',
                     'km','Anstieg','Teilnehmer','Fotos'])
    tours = _gq(Tour).order_by(Tour.tour_date.desc()).all()
    for t in tours:
        attending = TourParticipant.query.filter_by(tour_id=t.id, status='attending').count()
        photos    = TourPhoto.query.filter_by(tour_id=t.id).count()
        writer.writerow([
            t.id, t.title, t.tour_date.isoformat() if t.tour_date else '', t.status, t.difficulty,
            t.gpx_km or '', int(t.gpx_ascent) if t.gpx_ascent else '',
            attending, photos
        ])
    from flask import Response
    return Response(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': 'attachment; filename="touren.csv"'}
    )


# ─── admin_reset_pw was already defined – keep alias for completeness ─────────



@app.route('/touren/<int:tour_id>/ical')
@login_required
def tour_ical(tour_id):
    """Generate .ics calendar file for a tour."""
    tour = Tour.query.get_or_404(tour_id)

    # Build iCal manually – no extra lib needed
    start_time = tour.start_time or '09:00'
    hh, mm     = map(int, start_time.split(':'))
    dt_start   = f"{tour.tour_date.strftime('%Y%m%d') if tour.tour_date else '20000101'}T{hh:02d}{mm:02d}00"
    dt_end     = f"{tour.tour_date.strftime('%Y%m%d') if tour.tour_date else '20000101'}T{min(hh+4,23):02d}{mm:02d}00"
    dt_stamp   = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

    uid = f"tour-{tour.id}-{dt_stamp}@dejungenolen"
    location = tour.meeting_desc or ''
    if tour.meeting_lat and tour.meeting_lng:
        location += f' ({tour.meeting_lat},{tour.meeting_lng})'

    desc_parts = []
    if tour.difficulty:
        desc_parts.append(f'Schwierigkeit: {tour.difficulty_label}')
    if tour.gpx_km:
        desc_parts.append(f'Strecke: {tour.gpx_km} km')
    if tour.description:
        desc_parts.append(tour.description.replace('\n', '\\n'))
    desc_parts.append(f'Details: {app.config["BASE_URL"]}/touren/{tour.id}')
    desc = '\\n'.join(desc_parts)

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//De jungen Olen//Radgruppe//DE\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{dt_stamp}\r\n"
        f"DTSTART:{dt_start}\r\n"
        f"DTEND:{dt_end}\r\n"
        f"SUMMARY:🚴 {tour.title}\r\n"
        f"DESCRIPTION:{desc}\r\n"
        f"LOCATION:{location}\r\n"
        "STATUS:CONFIRMED\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    from flask import Response
    filename = f"tour_{tour.id}_{tour.tour_date}.ics"
    return Response(
        ics,
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ─── Mitgliederverzeichnis (B-08) ────────────────────────────────────────────

@app.route('/mitglieder')
@login_required
def mitglieder():
    users = _gq(User).filter_by(is_active=True).order_by(User.name).all()
    # Attach quick stats
    members_data = []
    for u in users:
        confirmed = TourParticipant.query.filter_by(
            user_id=u.id, confirmed_present=True
        ).count()
        members_data.append({'user': u, 'tour_count': confirmed,
                             'badges': compute_badges(u)})
    return render_template('mitglieder.html', members=members_data)


# ─── Foto-Challenge (C-05) ────────────────────────────────────────────────────

@app.route('/challenge')
@login_required
def foto_challenge():
    """Simple photo challenge: current month's theme from admin note."""
    # Use a simple config-in-DB approach: store challenge theme in a POI with
    # category='challenge' – no extra table needed for MVP.
    challenge = POI.query.filter_by(category='challenge', is_shared=True)\
                         .order_by(POI.created_at.desc()).first()

    # Recent photos from this month for the challenge
    from datetime import timedelta
    month_start = date.today().replace(day=1)
    recent_photos = (TourPhoto.query
                     .filter(TourPhoto.created_at >= month_start)
                     .order_by(TourPhoto.created_at.desc())
                     .limit(24).all())
    return render_template('challenge.html',
                           challenge=challenge,
                           recent_photos=recent_photos)


@app.route('/challenge/setzen', methods=['POST'])
@login_required
@organizer_required
def challenge_set():
    """Organizer sets the monthly challenge theme."""
    theme = request.form.get('theme', '').strip()
    if not theme:
        flash('Bitte ein Thema eingeben.', 'warning')
        return redirect(url_for('foto_challenge'))

    # Update or create challenge POI
    existing = POI.query.filter_by(category='challenge', is_shared=True).first()
    if existing:
        existing.name        = theme
        existing.description = request.form.get('description','').strip() or None
    else:
        poi = POI(name=theme, category='challenge',
                  lat=0, lng=0, is_shared=True,
                  description=request.form.get('description','').strip() or None,
                  added_by=current_user.id)
        db.session.add(poi)
    db.session.commit()
    flash(f'Challenge-Thema gesetzt: {theme}', 'success')
    send_telegram(
        f'📸 <b>Neue Foto-Challenge!</b>\n\n'
        f'Thema: <b>{theme}</b>\n'
        f'{request.form.get("description","")}\n\n'
        f'Macht mit! 👉 {app.config["BASE_URL"]}/challenge'
    )
    return redirect(url_for('foto_challenge'))


# ─── E-Mail Konfiguration (N-04) – Stub mit Flask-Mail ───────────────────────
# Aktivierung: pip install Flask-Mail, dann in .env setzen:
#   MAIL_SERVER=smtp.example.com  MAIL_USERNAME=...  MAIL_PASSWORD=...
#
# Einfacher Wrapper – sendet nur wenn Flask-Mail konfiguriert ist:

def send_email(to, subject, body_html):
    """Send email if Flask-Mail is configured (optional feature)."""
    mail_server = os.getenv('MAIL_SERVER', '')
    if not mail_server:
        app.logger.info(f'[E-Mail stub] To:{to} Subject:{subject}')
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = os.getenv('MAIL_FROM', 'noreply@dejungenolen.de')
        msg['To']      = to
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))
        with smtplib.SMTP_SSL(mail_server, int(os.getenv('MAIL_PORT', 465))) as s:
            s.login(os.getenv('MAIL_USERNAME',''), os.getenv('MAIL_PASSWORD',''))
            s.send_message(msg)
        return True
    except Exception as e:
        app.logger.error(f'E-Mail error: {e}')
        return False


# ─── Telegram Teilen-Link (N-03) ──────────────────────────────────────────────

@app.route('/touren/<int:tour_id>/telegram-teilen', methods=['POST'])
@login_required
@organizer_required
def tour_telegram_share(tour_id):
    """Send a tour link to the Telegram group."""
    tour = Tour.query.get_or_404(tour_id)
    msg  = (
        f'📖 <b>Tour im Archiv</b>\n\n'
        f'🚴 <b>{tour.title}</b>\n'
        f'📅 {tour.tour_date.strftime("%d.%m.%Y") if tour.tour_date else "Datum offen"}\n'
    )
    if tour.gpx_km:
        msg += f'📏 {tour.gpx_km} km'
    if tour.gpx_ascent:
        msg += f' · ⛰️ {int(tour.gpx_ascent)} m\n'
    else:
        msg += '\n'
    msg += f'👉 {app.config["BASE_URL"]}/touren/{tour.id}'
    send_telegram(msg)
    flash('Tour wurde im Telegram-Kanal geteilt!', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


# ─── Phase 4: PWA – Service Worker ────────────────────────────────────────────

@app.route('/sw.js')
def service_worker():
    """Serve service worker from root scope."""
    from flask import make_response, send_from_directory
    resp = make_response(send_from_directory('static', 'sw.js'))
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


# ─── Phase 4: Tour-PDF (druckfreundliche Ansicht) ─────────────────────────────

@app.route('/touren/<int:tour_id>/drucken')
@login_required
def tour_print(tour_id):
    tour = Tour.query.get_or_404(tour_id)
    attending = TourParticipant.query.filter_by(tour_id=tour_id, status='attending').all()

    gpx_data = None
    if tour.gpx_file:
        gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
        if os.path.exists(gpx_path):
            gpx_data = parse_gpx(gpx_path)

    photos = tour.photos.filter(
        TourPhoto.lat != None
    ).order_by(TourPhoto.created_at).all()

    return render_template('touren/print.html',
                           tour=tour,
                           attending=attending,
                           gpx_data=json.dumps(gpx_data) if gpx_data else 'null',
                           photos=photos,
                           today=date.today())


# ─── Phase 4: Heatmap-Daten API ───────────────────────────────────────────────

@app.route('/api/heatmap')
@login_required
def api_heatmap():
    """Return GPX tracks as polylines for overlay visualization."""
    tours = (_gq(Tour)
             .filter(Tour.status == 'completed', Tour.gpx_file != None)
             .order_by(Tour.tour_date.desc())
             .limit(50)  # max 50 Touren für Performance
             .all())

    tracks = []
    for t in tours:
        gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], t.gpx_file)
        if not os.path.exists(gpx_path):
            continue
        parsed = parse_gpx(gpx_path)
        if not parsed or not parsed.get('points'):
            continue
        pts = parsed['points']
        # Jeden 3. Punkt für kompakte Übertragung
        coords = [[p['lat'], p['lng']] for p in pts[::3]]
        if len(coords) < 2:
            continue
        tracks.append({
            'id':    t.id,
            'title': t.title,
            'date':  t.tour_date.strftime('%d.%m.%Y') if t.tour_date else '',
            'km':    t.gpx_km,
            'pts':   coords,
        })

    return jsonify({'tracks': tracks})


# ─── Phase 4: Dashboard context – Birthdays + "Vor X Jahren" ─────────────────

def upcoming_birthdays(days=30):
    """Return users whose birthday falls within the next `days` days, in the active group."""
    try:
        from datetime import timedelta
        today   = date.today()
        results = []
        users   = _gq(User).filter(User.birthday != None, User.is_active == True).all()
        for u in users:
            bday = u.birthday
            try:
                this_year = bday.replace(year=today.year)
            except ValueError:
                this_year = bday.replace(year=today.year, day=28)
            if this_year < today:
                try:
                    this_year = bday.replace(year=today.year + 1)
                except ValueError:
                    this_year = bday.replace(year=today.year + 1, day=28)
            delta = (this_year - today).days
            if 0 <= delta <= days:
                results.append({'user': u, 'date': this_year, 'days_until': delta})
        return sorted(results, key=lambda x: x['days_until'])
    except Exception:
        return []


def tours_this_day_past_years():
    """Tours from approx. same month in previous years, in the active group."""
    try:
        today   = date.today()
        tours   = _gq(Tour).filter(
            Tour.status == 'completed',
            db.extract('month', Tour.tour_date) == today.month,
            db.extract('year',  Tour.tour_date) <  today.year,
        ).order_by(Tour.tour_date.desc()).limit(5).all()
        return [{'tour': t, 'years_ago': today.year - t.tour_date.year if t.tour_date else 0} for t in tours]
    except Exception:
        return []


# ─── Error handlers ───────────────────────────────────────────────────────────
@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    import traceback as _tb
    tb = _tb.format_exc()
    app.logger.error(f'500: {tb}')
    try: db.session.rollback()
    except Exception: pass
    try:
        flash(f'Serverfehler: {e}', 'danger')
        return render_template('errors/500.html'), 500
    except Exception:
        return f'<pre>500:\n{tb}</pre>', 500


# ─── Web-Ersteinrichtung (kein Shell-Zugriff nötig) ───────────────────────────
# Aufruf: https://deine-domain.de/setup/SETUP_KEY
# SETUP_KEY wird in der .env-Datei gesetzt.
# Die Route ist dauerhaft deaktiviert sobald ein Admin-Konto existiert.

@app.route('/setup', methods=['GET'])
@app.route('/setup/<path:key>', methods=['GET', 'POST'])
def setup_wizard(key=''):
    """Web-basierte Ersteinrichtung ohne Shell-Zugriff."""
    setup_key = os.getenv('SETUP_KEY', '')

    # Prüfe ob schon ein Admin existiert → Setup sperren
    try:
        admin_exists = User.query.filter_by(role='admin').first() is not None
    except Exception:
        admin_exists = False

    if admin_exists:
        flash('Die App ist bereits eingerichtet. Setup deaktiviert.', 'info')
        return redirect(url_for('login'))

    # Wenn kein SETUP_KEY gesetzt: freier Zugang (nur solange kein Admin)
    if setup_key and key != setup_key:
        return render_template('setup.html',
                               step='key_required',
                               error='Ungültiger Setup-Schlüssel.')

    if request.method == 'GET':
        try:
            db.create_all()
            init_site_config()
        except Exception as e:
            app.logger.error(f'Setup DB init: {e}')
        return render_template('setup.html', step='form', key=key)

    # POST – Admin-Konto anlegen
    name     = request.form.get('name','').strip()
    email    = request.form.get('email','').strip().lower()
    pw       = request.form.get('password','').strip()
    pw2      = request.form.get('password2','').strip()
    tg_token = request.form.get('telegram_bot_token','').strip()
    tg_chat  = request.form.get('telegram_chat_id','').strip()
    base_url = request.form.get('base_url','').strip()

    errors = []
    if not name:        errors.append('Name fehlt.')
    if not email:       errors.append('E-Mail fehlt.')
    if pw != pw2:       errors.append('Passwörter stimmen nicht überein.')
    if len(pw) < 6:     errors.append('Passwort muss mindestens 6 Zeichen haben.')
    if User.query.filter_by(email=email).first():
        errors.append('Diese E-Mail ist bereits registriert.')

    if errors:
        return render_template('setup.html', step='form', key=key,
                               errors=errors, form=request.form)

    try:
        # Admin-User erstellen
        user = User(email=email, name=name, role='admin')
        user.set_password(pw)
        db.session.add(user)

        # Optionale Einstellungen speichern
        if tg_token: SiteConfig.set('telegram_bot_token', tg_token)
        if tg_chat:  SiteConfig.set('telegram_chat_id',   tg_chat)
        if base_url: SiteConfig.set('base_url', base_url)

        db.session.commit()
        login_user(user)
        flash(f'✅ Willkommen, {name}! Die App ist jetzt eingerichtet. '
              f'Erstelle Einladungslinks für weitere Mitglieder im Admin-Bereich.', 'success')
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        app.logger.error(f'Setup error: {e}')
        return render_template('setup.html', step='form', key=key,
                               errors=[f'Datenbankfehler: {e}'], form=request.form)


# ─── CLI: init DB + first admin ───────────────────────────────────────────────
@app.cli.command('init-db')
def init_db():
    db.create_all()
    init_site_config()
    print('Datenbank initialisiert + SiteConfig-Defaults gesetzt.')


@app.cli.command('create-admin')
def create_admin():
    """Interactive: create first admin user."""
    email = input('Admin E-Mail: ').strip()
    name  = input('Name: ').strip()
    pw    = input('Passwort: ').strip()
    if User.query.filter_by(email=email).first():
        print('E-Mail bereits registriert.')
        return
    user = User(email=email, name=name, role='admin')
    user.set_password(pw)
    db.session.add(user)
    db.session.commit()
    print(f'Admin "{name}" erstellt.')


# ─── Passenger WSGI entry point ───────────────────────────────────────────────
# Run migration at module import time so columns exist before any query fires
with app.app_context():
    try:
        from sqlalchemy import text as _text
        with db.engine.connect() as _conn:
            # 1. groups-Tabelle zuerst (FK-Ziel muss vor FK-Spalten existieren)
            _conn.execute(_text('''CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT, logo TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )'''))
            # Erste Gruppe anlegen falls leer
            _row = _conn.execute(_text("SELECT id FROM groups LIMIT 1")).fetchone()
            if not _row:
                _cfg = _conn.execute(_text("SELECT value FROM site_config WHERE key='group_name'")).fetchone()
                _gname = _cfg[0] if _cfg else 'De jungen Olen'
                _conn.execute(_text("INSERT INTO groups (slug, name) VALUES ('default', :n)"), {'n': _gname})
            _gid = _conn.execute(_text("SELECT id FROM groups LIMIT 1")).fetchone()[0]

            # 2. group_id Spalten direkt hinzufügen (ALTER TABLE IF NOT EXISTS column)
            for _tbl in ('users', 'tours', 'invite_tokens'):
                try:
                    _conn.execute(_text(f"ALTER TABLE {_tbl} ADD COLUMN group_id INTEGER DEFAULT {_gid}"))
                except Exception:
                    pass  # Spalte existiert bereits
            # Bestehende NULL-Zeilen zuordnen
            for _tbl in ('users', 'tours', 'invite_tokens'):
                try:
                    _conn.execute(_text(f"UPDATE {_tbl} SET group_id={_gid} WHERE group_id IS NULL"))
                except Exception:
                    pass
            _conn.commit()

        db.create_all()
        migrate_db()
        init_site_config()
        enable_wal()
    except Exception as _e:
        import logging
        logging.warning(f'Startup migration: {_e}')

if __name__ == '__main__':
    app.run(debug=True)
