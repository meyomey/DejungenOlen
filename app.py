import os
import re
import io
import secrets
import json
import subprocess
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, render_template, render_template_string, redirect, url_for, request,
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


def _tour_or_404(tour_id):
    """Tour laden; Nicht-Admins dürfen nur Touren der eigenen Gruppe sehen."""
    t = Tour.query.get_or_404(tour_id)
    try:
        if (current_user.is_authenticated and not current_user.is_admin
                and t.group_id and current_user.group_id
                and t.group_id != current_user.group_id):
            abort(404)
    except NameError:
        pass
    return t


def _own_group_or_404(obj):
    """Objekt mit group_id (Vorlage, Nutzer …): Nicht-Admins nur in der eigenen Gruppe."""
    if obj is None:
        abort(404)
    if (current_user.is_authenticated and not current_user.is_admin
            and getattr(obj, 'group_id', None) and current_user.group_id
            and obj.group_id != current_user.group_id):
        abort(404)
    return obj


def _photo_tour_or_404(photo):
    """Zur Foto-Tour gehörenden Gruppen-Check ausführen (Mandanten-Trennung)."""
    if photo is None or photo.tour_id is None:
        abort(404)
    return _tour_or_404(photo.tour_id)


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
                    GastroPhoto, TimeVote, LiveLocation, TourRide,
                    PasswordReset, GastroSpot, GastroReview, POI, TourComment, SiteConfig,
                    RouteRating, TourTemplate, PushSubscription, Announcement)

# ─── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config.from_object(Config)

# ─── Versionskennung (bei jeder Auslieferung hochzählen) ─────────────────────
APP_VERSION = '1.4.0'
APP_BUILD   = '2026-10-15 ae'   # Datum + Buchstabe pro Auslieferung am selben Tag


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return resp


# Audit 1.4.0: Private Uploads (Fotos, Videos, GPX, Avatare, Musik) liegen unter
# /static/uploads/… und wären sonst ohne Login für jeden abrufbar, der die URL kennt.
# Gruppen-Logos und Ankündigungsbilder bleiben öffentlich (Login-/Registrierungsseite).
_PRIVATE_UPLOAD_PREFIXES = tuple(
    f'/static/uploads/{d}/' for d in ('photos', 'videos', 'gpx', 'avatars', 'group_music'))


@app.before_request
def _protect_private_uploads():
    if request.path.startswith(_PRIVATE_UPLOAD_PREFIXES) and not current_user.is_authenticated:
        abort(404)


@app.context_processor
def inject_app_version():
    return {'app_version': APP_VERSION, 'app_build': APP_BUILD}
app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)

# .m4a wird von manchen Servern/Systemen falsch oder gar nicht als Audio erkannt,
# was Browser-seitiges decodeAudioData() unzuverlässig macht. Explizit registrieren.
import mimetypes as _mimetypes
_mimetypes.add_type('audio/mp4', '.m4a')
_mimetypes.add_type('audio/aac', '.aac')

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


# ─── Eingabe-Helfer (Audit 1.4.0) ────────────────────────────────────────────

def _safe_redirect_target(target):
    """Nur relative Pfade als Login-Weiterleitung zulassen (kein Open Redirect)."""
    if not target:
        return None
    target = target.strip()
    if target.startswith('/') and not target.startswith('//') and not target.startswith('/\\'):
        return target
    return None


def _clean_url(value):
    """Externe Links (Komoot, Webseite): nur http(s). Ohne Schema wird https:// ergänzt,
    andere Schemata (javascript:, data:, …) werden verworfen."""
    value = (value or '').strip()
    if not value:
        return None
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*:', value):
        return value if value.lower().startswith(('http://', 'https://')) else None
    return 'https://' + value


def _parse_float(value, default=None):
    """Formularwert → float; leere/ungültige Eingaben ergeben default statt 500."""
    value = (value or '').strip().replace(',', '.')
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_int(value, default=None):
    value = (value or '').strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_date(value, default=None):
    """Formularwert 'YYYY-MM-DD' → date; ungültig → default statt 500."""
    value = (value or '').strip()
    if not value:
        return default
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return default


def _json_for_script(obj):
    """JSON zum Einbetten in <script>-Blöcke: <, > und & werden als \\uXXXX
    maskiert, damit ein '</script>' in Nutzerdaten den Block nicht beenden kann."""
    return (json.dumps(obj)
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


def _tile_xy(lat, lng, zoom):
    """OSM-Kachel-Koordinaten (x,y) für eine Position bei gegebenem Zoom-Level."""
    import math
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat*math.pi/180.0) + 1.0/math.cos(lat*math.pi/180.0)) / math.pi) / 2.0 * n)
    return x, y


def _tile_bounds(x, y, zoom):
    """Lat/Lng-Grenzen einer Kachel (für die Kartendarstellung)."""
    import math
    n = 2 ** zoom
    lng1 = x / n * 360.0 - 180.0
    lng2 = (x+1) / n * 360.0 - 180.0
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2*y/n))))
    lat2 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2*(y+1)/n))))
    return {'south': min(lat1,lat2), 'north': max(lat1,lat2),
            'west': lng1, 'east': lng2}


def cfg(key, default=None):
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
    _v = SiteConfig.DEFAULTS.get(key, '')
    return _v if (_v or default is None) else default


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



def _get_vapid_keys():
    """Holt (oder erzeugt einmalig) das VAPID-Schlüsselpaar für Web Push,
    gespeichert in SiteConfig. Gibt (private_key_b64url, public_key_b64url)
    zurück, oder (None, None) wenn 'pywebpush'/'cryptography' nicht installiert
    sind.

    WICHTIG: pywebpush's Vapid.from_string() erwartet den ROHEN, base64url-
    kodierten privaten Schlüssel (32 Byte) – KEIN PEM-Format! Ein PEM-String
    lässt sich damit nicht deserialisieren."""
    try:
        from py_vapid import Vapid02 as Vapid
    except Exception:
        return None, None

    priv = cfg('vapid_private_key')
    pub  = cfg('vapid_public_key')

    # Selbstreparatur: eine ältere Version dieser Funktion hat fälschlich das
    # PEM-Format gespeichert (mit "-----BEGIN..."), das pywebpush nicht lesen
    # kann. Prüfen ob der gespeicherte Wert wirklich ein roher base64url-String
    # ist (kein PEM-Header, plausible Länge) – sonst verwerfen und neu erzeugen.
    def _looks_valid_raw_key(k, expected_len):
        if not k or '-----BEGIN' in k or '\n' in k:
            return False
        return abs(len(k) - expected_len) <= 2  # etwas Toleranz für Padding

    if priv and pub and not (_looks_valid_raw_key(priv, 43) and _looks_valid_raw_key(pub, 87)):
        app.logger.warning('VAPID-Schlüssel im alten/ungültigen Format gefunden – werden neu erzeugt.')
        priv, pub = None, None
        # Alle bestehenden Subscriptions sind an den ALTEN (nie funktionsfähigen)
        # Public Key gebunden und damit ohnehin nutzlos – aufräumen, damit
        # Nutzer sauber neu aktivieren statt auf eine kaputte Subscription zu treffen.
        try:
            PushSubscription.query.delete()
            db.session.commit()
        except Exception:
            db.session.rollback()

    if priv and pub:
        return priv, pub

    try:
        import base64
        from cryptography.hazmat.primitives import serialization

        vapid = Vapid()
        vapid.generate_keys()

        # Privaten Schlüssel als rohe 32-Byte-Zahl, base64url-kodiert
        priv_numbers = vapid.private_key.private_numbers()
        raw_priv = priv_numbers.private_value.to_bytes(32, 'big')
        priv_b64 = base64.urlsafe_b64encode(raw_priv).decode().rstrip('=')

        # Öffentlichen Schlüssel als unkomprimierten EC-Punkt (65 Byte), base64url
        raw_pub = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        pub_b64 = base64.urlsafe_b64encode(raw_pub).decode().rstrip('=')

        SiteConfig.set('vapid_private_key', priv_b64)
        SiteConfig.set('vapid_public_key', pub_b64)
        db.session.commit()
        return priv_b64, pub_b64
    except Exception as e:
        app.logger.warning(f'VAPID-Schlüsselerzeugung fehlgeschlagen: {e}')
        return None, None


def send_push(subscription, title, body, url=None):
    """Sendet eine einzelne Web-Push-Benachrichtigung.
    Gibt (erfolgreich: bool, grund: str) zurück – der Grund hilft beim
    Debuggen, falls der Versand fehlschlägt."""
    try:
        from pywebpush import webpush, WebPushException
    except Exception as e:
        return False, f'pywebpush nicht installiert ({e})'

    priv_key, pub_key = _get_vapid_keys()
    if not priv_key:
        return False, 'VAPID-Schlüssel konnten nicht erzeugt werden (py_vapid/cryptography fehlt?)'

    payload = json.dumps({
        'title': title, 'body': body,
        'url': url or '/', 'icon': '/static/logo.png',
    })
    try:
        webpush(
            subscription_info={
                'endpoint': subscription.endpoint,
                'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
            },
            data=payload,
            vapid_private_key=priv_key,
            vapid_claims={'sub': f'mailto:{cfg("admin_email") or "admin@example.de"}'},
        )
        return True, 'ok'
    except WebPushException as e:
        status = getattr(e.response, 'status_code', None)
        body_text = ''
        try:
            body_text = e.response.text[:200] if e.response is not None else ''
        except Exception:
            pass
        if status in (404, 410):
            # Subscription ist nicht mehr gültig (Browser abgemeldet, App deinstalliert etc.)
            try:
                db.session.delete(subscription)
                db.session.commit()
            except Exception:
                pass
            return False, f'Subscription ungültig (HTTP {status}) – wurde entfernt, bitte neu aktivieren'
        app.logger.warning(f'Push-Fehler ({status}): {e}')
        return False, f'HTTP {status}: {body_text or str(e)[:200]}'
    except Exception as e:
        app.logger.warning(f'Push-Fehler: {e}')
        return False, f'{type(e).__name__}: {str(e)[:200]}'


def send_push_to_user(user, title, body, url=None):
    """Sendet eine Push-Benachrichtigung an alle Geräte eines Nutzers.
    Gibt (anzahl_erfolgreich, liste_der_gründe) zurück – letztere hilft beim
    Debuggen, falls kein Versand geklappt hat."""
    subs = PushSubscription.query.filter_by(user_id=user.id).all()
    sent = 0
    reasons = []
    if not subs:
        return 0, ['Keine Push-Subscription für diesen Nutzer gespeichert. '
                    'Erst „Benachrichtigungen aktivieren" anklicken.']
    for sub in subs:
        ok, reason = send_push(sub, title, body, url)
        if ok:
            sent += 1
        reasons.append(reason)
    return sent, reasons


def send_push_to_group(group_id, title, body, url=None, exclude_user_id=None):
    """Sendet eine Push-Benachrichtigung an alle Mitglieder einer Gruppe."""
    if not group_id:
        return 0
    users = User.query.filter_by(group_id=group_id, is_active=True).all()
    sent = 0
    for u in users:
        if exclude_user_id and u.id == exclude_user_id:
            continue
        n, _ = send_push_to_user(u, title, body, url)
        sent += n
    return sent


def _tg(value):
    """Build ab: Nutzertext für Telegram (parse_mode HTML) entschärfen – ein „<3“ oder
    ein „<b>“ im Tourtitel würde sonst die ganze Nachricht ungültig machen bzw. als
    Formatierung wirken."""
    import html as _html
    return _html.escape(str(value if value is not None else ''), quote=False)


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

        gps_info = {}
        with Image.open(filepath) as img:            # Build ac: Datei wieder schließen (ResourceWarning)
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


def _exif_datetime_from_tiff(exif_data):
    """Build ac: TIFF-Block (ab der Byte-Order-Marke) → Aufnahmezeit. Reihenfolge:
    DateTimeOriginal (36867, liegt im Exif-Unter-IFD) → DateTimeDigitized (36868) → DateTime
    (306 im IFD0 – das ist bei bearbeiteten Fotos das Änderungsdatum, deshalb nur als Notnagel).
    Vorher wurde nur das IFD0 gelesen, also meist das Änderungsdatum."""
    import struct
    bom = exif_data[:2]
    if bom == b'II':
        endian = '<'
    elif bom == b'MM':
        endian = '>'
    else:
        return None

    def _read_ifd(ifd):
        found, exif_ptr = {}, None
        num = struct.unpack_from(f'{endian}H', exif_data, ifd)[0]
        for n in range(min(num, 500)):
            off = ifd + 2 + n * 12
            if off + 12 > len(exif_data):
                break
            tag, typ, cnt = struct.unpack_from(f'{endian}HHI', exif_data, off)
            if tag == 34665:                                   # Zeiger auf das Exif-Unter-IFD
                exif_ptr = struct.unpack_from(f'{endian}I', exif_data, off + 8)[0]
            elif tag in (36867, 36868, 306) and typ == 2:      # ASCII "YYYY:MM:DD HH:MM:SS"
                voff = struct.unpack_from(f'{endian}I', exif_data, off + 8)[0] if cnt > 4 else off + 8
                raw = exif_data[voff:voff + cnt]
                found[tag] = raw.split(b'\x00', 1)[0].decode('ascii', errors='ignore').strip()
        return found, exif_ptr

    ifd0 = struct.unpack_from(f'{endian}I', exif_data, 4)[0]
    found, exif_ptr = _read_ifd(ifd0)
    if exif_ptr and 8 <= exif_ptr < len(exif_data) - 2:
        try:
            sub, _ = _read_ifd(exif_ptr)
            for tag, val in sub.items():
                found.setdefault(tag, val)
        except Exception:
            pass
    for tag in (36867, 36868, 306):
        val = found.get(tag)
        if val:
            try:
                return datetime.strptime(val[:19], '%Y:%m:%d %H:%M:%S')
            except ValueError:
                continue
    return None


def extract_datetime_from_exif(filepath):
    """Aufnahmezeit aus EXIF (JPEG-APP1 oder der in HEIC eingebettete Exif-Block) als naive
    Ortszeit, sonst None. Build ac: liest DateTimeOriginal aus dem Exif-Unter-IFD (vorher nur
    IFD0 = meist Änderungsdatum) und versteht HEIC; Pillow als letzter Versuch."""
    try:
        with open(filepath, 'rb') as f:
            data = f.read(2 * 1024 * 1024)      # EXIF steht vorn – bei HEIC ggf. hinter den Meta-Boxen

        exif_data = None
        if data[:2] == b'\xff\xd8':                            # JPEG: APP1-Segment "Exif\0\0" suchen
            i = 0
            while i < min(len(data), 65536) - 4:
                if data[i] == 0xFF and data[i + 1] == 0xE1:
                    length = (data[i + 2] << 8) | data[i + 3]
                    seg = data[i + 4:i + 2 + length]
                    if seg[:4] == b'Exif':
                        exif_data = seg[6:]
                        break
                i += 1
        elif len(data) >= 12 and data[4:8] in (b'ftyp', b'mif1', b'msf1'):   # HEIC/HEIF
            idx = 0
            while True:
                idx = data.find(b'Exif\x00\x00', idx)
                if idx < 0:
                    break
                chunk = data[idx + 6:idx + 6 + 65536]
                if chunk[:2] in (b'II', b'MM'):
                    exif_data = chunk
                    break
                idx += 4

        if exif_data:
            found = _exif_datetime_from_tiff(exif_data)
            if found:
                return found
    except Exception:
        pass

    # Letzter Versuch: Pillow (liest auch exotische Varianten, kann aber kein HEIC)
    try:
        if _pillow_ok():
            from PIL import Image as _PILImage
            with _PILImage.open(filepath) as img:
                ex = img.getexif()
                val = None
                try:
                    val = ex.get_ifd(0x8769).get(36867)
                except Exception:
                    val = None
                val = val or ex.get(306)
                if val:
                    return datetime.strptime(str(val)[:19], '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
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
    wa_link   = ''
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
        try:
            wa_link = (cfg('whatsapp_group_link') or '').strip()
        except Exception:
            pass
    return dict(upcoming_tours=upcoming, today_date=date.today(),
                telegram_username=tg_user,
                telegram_invite_link=tg_invite,
                telegram_link=tg_link,
                whatsapp_link=wa_link)

# Make Python's enumerate available in templates
app.jinja_env.globals['enumerate'] = enumerate
app.jinja_env.globals['hasattr']   = hasattr


# ─── Auth routes ──────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    # Audit 1.4.0: Frische Installation (noch kein Admin) → direkt zum Setup-Wizard,
    # wie in der Installationsanleitung beschrieben („erscheint automatisch“)
    if request.method == 'GET':
        try:
            if User.query.filter_by(role='admin').first() is None:
                return redirect(url_for('setup_wizard'))
        except Exception:
            pass
    # Öffentliche Ankündigungen – ohne group_id = gruppenübergreifend, da vor dem
    # Login noch kein Gruppen-Kontext feststeht
    login_announcements = get_visible_announcements(group_id=None, context='logged_out')
    login_contact_email = cfg('contact_email')
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        # Rate limiting: max 10 Login-Versuche pro IP pro Minute
        ip = request.remote_addr or 'unknown'
        if _rate_limit(f'login:{ip}', max_calls=10, window=60):
            flash('Zu viele Versuche. Bitte eine Minute warten.', 'danger')
            return render_template('auth/login.html', announcements=login_announcements,
                                   contact_email=login_contact_email)
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
            return redirect(_safe_redirect_target(request.args.get('next')) or url_for('index'))
        flash('E-Mail oder Passwort falsch.', 'danger')
    return render_template('auth/login.html', announcements=login_announcements,
                           contact_email=login_contact_email,
                           mail_configured=bool(os.getenv('MAIL_SERVER')))   # Build ab: Anmelde-Link


LOGIN_LINK_MSG = ('Falls diese E-Mail-Adresse registriert ist, wurde ein Anmelde-Link verschickt. '
                  'Bitte auch den Spam-Ordner prüfen. Der Link ist 15 Minuten gültig.')


@app.route('/login-link', methods=['POST'])
def login_link_request():
    """Build ab: Anmelden ohne Passwort – ein einmaliger Link per E-Mail (15 Minuten gültig).
    Gedacht für Mitglieder, die sich ihr Passwort nicht merken wollen; Antwort verrät nicht,
    ob die Adresse existiert."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    email = request.form.get('email', '').strip().lower()
    ip = request.remote_addr or 'unknown'
    if _rate_limit(f'loginlink:{ip}', max_calls=5, window=300):
        flash('Zu viele Anfragen. Bitte 5 Minuten warten.', 'danger')
        return redirect(url_for('login'))
    if not email or '@' not in email:
        flash('Bitte zuerst deine E-Mail-Adresse eintragen.', 'warning')
        return redirect(url_for('login'))
    if not os.getenv('MAIL_SERVER'):
        flash('E-Mail-Versand ist nicht eingerichtet – bitte mit Passwort anmelden.', 'warning')
        return redirect(url_for('login'))
    user = User.query.filter_by(email=email).first()
    if user and user.is_active and not _rate_limit(f'loginlink:user:{user.id}', max_calls=3, window=3600):
        token = secrets.token_urlsafe(32)
        db.session.add(PasswordReset(user_id=user.id, token=token, purpose='login'))
        db.session.commit()
        link = url_for('login_link', token=token, _external=True)
        send_mail(to=user.email, subject=f'{cfg("site_name") or "De jungen Olen"} – dein Anmelde-Link',
                  body=(f'Moin {user.display_name},\n\n'
                        f'mit diesem Link bist du sofort angemeldet (15 Minuten gültig, einmal nutzbar):\n'
                        f'{link}\n\n'
                        f'Falls du das nicht warst, ignoriere diese E-Mail einfach.\n\n'
                        f'{cfg("site_name") or "De jungen Olen"}'))
    flash(LOGIN_LINK_MSG, 'info')
    return redirect(url_for('login'))


@app.route('/anmelden/<token>')
def login_link(token):
    """Build ab: Einmal-Link aus der E-Mail einlösen → angemeldet (dauerhaft, wie „Angemeldet bleiben“)."""
    pr = PasswordReset.query.filter_by(token=token, used=False, purpose='login').first()
    if (pr is None or pr.user is None or not pr.user.is_active or not pr.created_at
            or pr.created_at < datetime.utcnow() - timedelta(minutes=15)):
        flash('Dieser Anmelde-Link ist ungültig oder abgelaufen – bitte einen neuen anfordern.', 'warning')
        return redirect(url_for('login'))
    pr.used = True
    pr.user.last_login = datetime.utcnow()
    login_user(pr.user, remember=True)
    db.session.commit()
    flash(f'Willkommen, {pr.user.display_name}!', 'success')
    return redirect(url_for('index'))


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
        if len(pw) < 8:
            flash('Passwort muss mindestens 8 Zeichen haben.', 'danger')
            return render_template('auth/register.html', invite=invite)
        if User.query.filter_by(email=email).first():
            flash('Diese E-Mail ist bereits registriert.', 'danger')
            return render_template('auth/register.html', invite=invite)

        user = User(email=email, name=name, nickname=nickname,
                    bicycle_type=bicycle, is_ebike=ebike,
                    group_id=invite.group_id)
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
    pr = (PasswordReset.query.filter_by(token=token, used=False)
          .filter(db.or_(PasswordReset.purpose == None, PasswordReset.purpose == 'reset'))   # noqa: E711  Build ab
          .first_or_404())
    # Audit 1.4.0: Link ist (wie in der Mail versprochen) nur 1 Stunde gültig
    if pr.user is None or not pr.created_at or \
            pr.created_at < datetime.utcnow() - timedelta(hours=1):
        flash('Dieser Link ist abgelaufen. Bitte fordere einen neuen Reset-Link an.', 'warning')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        pw  = request.form.get('password', '')
        pw2 = request.form.get('password2', '')
        if pw != pw2 or len(pw) < 8:
            flash('Passwörter stimmen nicht überein oder mindestens 8 Zeichen nötig.', 'danger')
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

    from flask import g as _g_idx
    _grp_idx = getattr(_g_idx, 'group', None)
    return render_template('index.html', upcoming=upcoming, recent=recent,
                           today=today,
                           geplante_touren=geplante,
                           cover_photos=cover_photos,
                           birthdays=upcoming_birthdays(),
                           memories=tours_this_day_past_years(),
                           milestones=group_milestones(),
                           announcements=get_visible_announcements(_grp_idx.id if _grp_idx else None))


# ─── Tour routes ──────────────────────────────────────────────────────────────
@app.route('/api/gpx/<int:tour_id>')
@login_required
def api_gpx_preview(tour_id):
    """Vereinfachte GPX-Punkte für Kartenvorschau."""
    tour = _tour_or_404(tour_id)
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

    # Build x: Organisatoren sehen, welche Touren der letzten 14 Tage noch keine bestätigte Anwesenheit haben
    attendance_todo = []
    if current_user.is_organizer or current_user.is_admin:
        try:
            from flask import g as _g_list
            _grp_list = getattr(_g_list, 'group', None)
            attendance_todo = _attendance_todo(_grp_list.id if _grp_list else None, today)
        except Exception as e:
            app.logger.warning(f'attendance_todo: {e}')

    return render_template('touren/list.html',
                           tours=tours_dated, tours_open=tours_open,
                           today=today, weather_map={},
                           default_lat=default_lat, default_lng=default_lng,
                           cover_photos=cover_photos, rating_map=rating_map,
                           attendance_todo=attendance_todo)


@app.route('/touren/vorlagen')
@login_required
@organizer_required
def tour_templates():
    """Übersicht aller gespeicherten Tour-Vorlagen der aktiven Gruppe."""
    templates = _gq(TourTemplate).order_by(TourTemplate.name).all()
    return render_template('touren/vorlagen.html', templates=templates)


@app.route('/touren/<int:tour_id>/als-vorlage', methods=['POST'])
@login_required
@organizer_required
def tour_save_as_template(tour_id):
    """Speichert eine bestehende Tour als wiederverwendbare Vorlage."""
    tour = _tour_or_404(tour_id)
    name = request.form.get('template_name', '').strip() or tour.title

    new_gpx_file = None
    if tour.gpx_file:
        src = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
        if os.path.exists(src):
            import shutil
            new_gpx_file = f'template_{secrets.token_hex(6)}.gpx'
            dst = os.path.join(app.config['UPLOAD_FOLDER_GPX'], new_gpx_file)
            shutil.copy2(src, dst)

    from flask import g as _g
    tmpl = TourTemplate(
        name          = name,
        title         = tour.title,
        description   = tour.description,
        difficulty    = tour.difficulty,
        approx_km     = tour.approx_km,
        external_link = tour.external_link,
        gpx_file      = new_gpx_file,
        gpx_km        = tour.gpx_km,
        gpx_ascent    = tour.gpx_ascent,
        meeting_lat   = tour.meeting_lat,
        meeting_lng   = tour.meeting_lng,
        meeting_desc  = tour.meeting_desc,
        default_start_time = tour.start_time,
        created_by    = current_user.id,
        group_id      = getattr(_g, 'group', None).id if getattr(_g, 'group', None) else None,
    )
    db.session.add(tmpl)
    db.session.commit()
    flash(f'Vorlage „{name}" gespeichert. Für wiederkehrende Touren jetzt unter „Vorlagen" verfügbar.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


@app.route('/touren/vorlagen/<int:template_id>/loeschen', methods=['POST'])
@login_required
@organizer_required
def tour_template_delete(template_id):
    """Löscht eine Tour-Vorlage."""
    tmpl = _own_group_or_404(TourTemplate.query.get_or_404(template_id))
    if tmpl.gpx_file:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER_GPX'], tmpl.gpx_file))
        except Exception:
            pass
    name = tmpl.name
    db.session.delete(tmpl)
    db.session.commit()
    flash(f'Vorlage „{name}" gelöscht.', 'success')
    return redirect(url_for('tour_templates'))


@app.route('/touren/neu/aus-vorlage/<int:template_id>', methods=['POST'])
@login_required
@organizer_required
def tour_create_from_template(template_id):
    """Erstellt sofort eine neue Tour (ohne Termin) aus einer Vorlage."""
    tmpl = _own_group_or_404(TourTemplate.query.get_or_404(template_id))

    new_gpx_file = None
    if tmpl.gpx_file:
        src = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tmpl.gpx_file)
        if os.path.exists(src):
            import shutil
            new_gpx_file = f'tour_from_tmpl_{secrets.token_hex(6)}.gpx'
            dst = os.path.join(app.config['UPLOAD_FOLDER_GPX'], new_gpx_file)
            shutil.copy2(src, dst)

    from flask import g as _g
    tour = Tour(
        title         = tmpl.title,
        description   = tmpl.description,
        tour_date     = date(9999, 12, 31),   # Datum noch offen – Organizer legt es fest
        start_time    = tmpl.default_start_time,
        difficulty    = tmpl.difficulty,
        approx_km     = tmpl.approx_km,
        external_link = tmpl.external_link,
        gpx_file      = new_gpx_file,
        gpx_km        = tmpl.gpx_km,
        gpx_ascent    = tmpl.gpx_ascent,
        meeting_lat   = tmpl.meeting_lat,
        meeting_lng   = tmpl.meeting_lng,
        meeting_desc  = tmpl.meeting_desc,
        created_by    = current_user.id,
        group_id      = getattr(_g, 'group', None).id if getattr(_g, 'group', None) else None,
    )
    db.session.add(tour)

    tmpl.use_count = (tmpl.use_count or 0) + 1
    tmpl.last_used_at = datetime.utcnow()

    db.session.commit()
    flash(f'Tour „{tour.title}" aus Vorlage erstellt. Jetzt Termin festlegen!', 'success')
    return redirect(url_for('tour_detail', tour_id=tour.id))


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

        # Audit 1.4.0: ungültiges Datum → Hinweis statt 500
        parsed_date = _parse_date(tour_date)
        if tour_date and parsed_date is None:
            flash('Ungültiges Datum. Bitte im Format JJJJ-MM-TT auswählen.', 'danger')
            return render_template('touren/create.html',
                                   difficulties=Config.DIFFICULTY_CHOICES)

        from flask import g as _g_create
        _grp_create = getattr(_g_create, 'group', None)
        tour = Tour(
            title         = title,
            description   = desc,
            tour_date     = parsed_date if parsed_date else date(9999, 12, 31),
            start_time    = start_time or None,
            difficulty    = difficulty,
            approx_km     = _parse_float(approx_km),
            external_link = _clean_url(external_link),
            meeting_lat   = _parse_float(meet_lat),
            meeting_lng   = _parse_float(meet_lng),
            meeting_desc  = meet_desc or None,
            created_by    = current_user.id,
            group_id      = _grp_create.id if _grp_create else None,
        )
        # Marker for "date open" - we use 9999-12-31 as sentinel value
        # because SQLite cannot ALTER COLUMN to remove NOT NULL constraint
        tour._date_open = not bool(tour_date)
        _apply_einkehr_form(tour)                      # Build x: geplante Einkehr
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
                _tour_apply_gpx_metrics(tour, parsed)          # Build w
        elif proposal_gpx:
            # Audit 1.4.0: nur Dateinamen aus dem GPX-Ordner zulassen (kein Path Traversal)
            proposal_gpx = os.path.basename(proposal_gpx)
            src = os.path.join(app.config['UPLOAD_FOLDER_GPX'], proposal_gpx)
            if proposal_gpx.lower().endswith('.gpx') and os.path.isfile(src):
                import shutil
                new_fname = f'tour_{tour.id}_{secrets.token_hex(4)}.gpx'
                dst = os.path.join(app.config['UPLOAD_FOLDER_GPX'], new_fname)
                shutil.copy2(src, dst)
                tour.gpx_file = new_fname
                parsed = parse_gpx(dst)
                if parsed:
                    tour.gpx_km     = parsed.get('km')
                    tour.gpx_ascent = parsed.get('ascent')
                    _tour_apply_gpx_metrics(tour, parsed)      # Build w

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
                f'📋 <b>{_tg(title)}</b>\n'
                f'📅 {datum}'
                f'{" um " + _tg(start_time) + " Uhr" if start_time and not tour.is_date_open else ""}\n'
                f'{km_str}'
                f'💪 Schwierigkeit: {_tg(tour.difficulty_label)}\n'
            )
            if meet_desc:
                tg_msg += f'📍 Treffpunkt: {_tg(meet_desc)}\n'
            tg_msg += f'\n👉 {app.config["BASE_URL"]}/touren/{tour.id}'
            send_telegram(tg_msg)
        except Exception as e:
            app.logger.warning(f'Telegram notification failed: {e}')

        # Push-Benachrichtigung an alle Gruppenmitglieder (außer Ersteller)
        try:
            push_body = f'{tour.difficulty_label}'
            if not tour.is_date_open:
                push_body += f' · {tour.tour_date.strftime("%d.%m.%Y")}'
            if tour.gpx_km:
                push_body += f' · {tour.gpx_km} km'
            send_push_to_group(
                tour.group_id,
                title=f'🚴 Neue Tour: {title}',
                body=push_body,
                url=f'/touren/{tour.id}',
                exclude_user_id=current_user.id,
            )
        except Exception as e:
            app.logger.warning(f'Push notification (tour_create) failed: {e}')

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


@__import__('functools').lru_cache(maxsize=16)      # Build ab: 64 → 16 (ca. 40 MB statt 170 MB bei großen Tracks)
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

        # Build j: Zeitstempel auswerten (sofern der Track welche hat) → Fahrzeit,
        # Gesamtzeit inkl. Pausen, Schnitt, Spitze, Start/Ende als Ortszeit.
        # Tracks ohne Zeiten liefern None – die Video-Folien lassen die Kacheln dann weg.
        ride = {'moving_s': None, 'total_s': None, 'avg_kmh': None, 'max_kmh': None,
                'start_time': None, 'end_time': None}
        try:
            md = gpx.get_moving_data()           # Pausen = Abschnitte langsamer als 1 km/h
            if md and md.moving_time and md.moving_time >= 60:
                ride['moving_s'] = int(md.moving_time)
                ride['total_s']  = int(gpx.get_duration() or 0) or None
                ride['avg_kmh']  = round(km / (md.moving_time / 3600), 1) if km else None
                if md.max_speed:
                    ride['max_kmh'] = round(md.max_speed * 3.6, 1)
                tb = gpx.get_time_bounds()
                if tb and tb.start_time and tb.end_time:
                    try:
                        from datetime import timezone as _utc
                        from zoneinfo import ZoneInfo
                        _tz = ZoneInfo('Europe/Berlin')

                        def _local(t):
                            if t.tzinfo is None:
                                t = t.replace(tzinfo=_utc.utc)
                            return t.astimezone(_tz).strftime('%H:%M')
                        ride['start_time'], ride['end_time'] = _local(tb.start_time), _local(tb.end_time)
                    except Exception:
                        pass
        except Exception as e:
            app.logger.warning(f'GPX moving data: {e}')

        return {'points': points, 'km': km, 'ascent': int(ascent), **ride}
    except Exception as e:
        app.logger.error(f'GPX parse error: {e}')
        return None


GPX_PAGE_MAX_PTS = 2000   # Build ab: mehr Punkte landen nicht mehr im HTML der Tour-Seite


def _thin_points(points, max_pts=GPX_PAGE_MAX_PTS):
    """Build ab: GPX-Punkte (dicts mit lat/lng/ele) auf höchstens max_pts reduzieren.
    Douglas-Peucker in 3D (Lage in Metern + Höhe), damit ein Hügel auf gerader Straße
    im Höhenprofil nicht verschwindet; die Toleranz wird verdoppelt, bis es passt.
    Die Punkt-Objekte selbst bleiben erhalten (Reihenfolge, alle Schlüssel)."""
    import math
    n = len(points)
    if n <= max_pts:
        return points
    idx = list(range(n))
    if n > 12000:                                        # Vorab ausdünnen: hält die Rechenzeit klein
        step = n // 12000 + 1
        idx = idx[::step]
        if idx[-1] != n - 1:
            idx.append(n - 1)
    mid = sum(float(points[i]['lat']) for i in idx) / len(idx)
    m_lat, m_lng = 111320.0, 111320.0 * max(0.2, math.cos(math.radians(mid)))
    xyz = [(float(points[i]['lat']) * m_lat, float(points[i]['lng']) * m_lng,
            float(points[i].get('ele') or 0.0)) for i in idx]

    def rdp(tol):
        keep = [False] * len(xyz)
        keep[0] = keep[-1] = True
        stack = [(0, len(xyz) - 1)]
        while stack:
            a, b = stack.pop()
            if b <= a + 1:
                continue
            ax, ay, az = xyz[a]
            dx, dy, dz = xyz[b][0] - ax, xyz[b][1] - ay, xyz[b][2] - az
            seg = dx * dx + dy * dy + dz * dz
            best_d, best_i = -1.0, a
            for i in range(a + 1, b):
                px, py, pz = xyz[i][0] - ax, xyz[i][1] - ay, xyz[i][2] - az
                t = max(0.0, min(1.0, (px * dx + py * dy + pz * dz) / seg)) if seg else 0.0
                d = math.sqrt((px - t * dx) ** 2 + (py - t * dy) ** 2 + (pz - t * dz) ** 2)
                if d > best_d:
                    best_d, best_i = d, i
            if best_d > tol:
                keep[best_i] = True
                stack.append((a, best_i))
                stack.append((best_i, b))
        return [i for i, k in zip(idx, keep) if k]

    tol, out = 2.0, idx
    while len(out) > max_pts and tol < 5000:
        out = rdp(tol)
        tol *= 2
    if len(out) > max_pts:                               # Notnagel: gleichmäßig ausdünnen
        step = len(out) // max_pts + 1
        out = out[::step] + [out[-1]]
    return [points[i] for i in out]


@__import__('functools').lru_cache(maxsize=16)
def gpx_for_page(filepath):
    """Build ab: parse_gpx-Ergebnis mit auf GPX_PAGE_MAX_PTS ausgedünnten Punkten – für das
    JSON in Tour-Detail, Druckansicht und Video-Seite. km/Anstieg bleiben die exakten Werte."""
    data = parse_gpx(filepath)
    if not data or not data.get('points'):
        return data
    return {**data, 'points': _thin_points(data['points'])}


# ─── Build ac: Fotos ohne Standort per Aufnahmezeit auf dem Track platzieren ──────────────────
# Handys entfernen beim Hochladen aus der Galerie den Standort, die Aufnahmezeit bleibt aber.
# Hat der GPX der Tour Zeitstempel (Aufzeichnung, keine geplante Route), wissen wir, wo die
# Gruppe zu dieser Uhrzeit war – das Foto bekommt diese Position als „geschätzt“ (gps_source='track').
PHOTO_TRACK_TOLERANCE_S = 15 * 60   # bis 15 min vor Start / nach Ende → erster bzw. letzter Punkt
PHOTO_TRACK_GAP_S       = 10 * 60   # bei längeren Lücken (Gerät aus) nicht interpolieren


def _gpx_timed_points(filepath):
    """Trackpunkte MIT Zeitstempel als zeitlich sortierte Liste (unix_ts, lat, lng); [] wenn der
    Track keine Zeiten hat oder nicht lesbar ist. Zeiten ohne Zone gelten als UTC (so schreiben
    es Garmin, Komoot und Wahoo), Punkte ohne <time> werden übersprungen."""
    try:
        import gpxpy
        from datetime import timezone as _tz
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            gpx = gpxpy.parse(f)
        out = []
        for track in gpx.tracks:
            for seg in track.segments:
                for pt in seg.points:
                    if pt.time is None:
                        continue
                    t = pt.time if pt.time.tzinfo else pt.time.replace(tzinfo=_tz.utc)
                    out.append((t.timestamp(), pt.latitude, pt.longitude))
        out.sort()
        return out
    except Exception as e:
        app.logger.warning(f'GPX Zeitstempel: {e}')
        return []


def _tour_timed_points(tour):
    """Zeitstempel-Punkte des Tour-GPX oder [] (kein GPX / Datei fehlt / keine Zeiten)."""
    if not tour.gpx_file:
        return []
    path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
    if not os.path.exists(path):
        return []
    return _gpx_timed_points(path)


def _track_position_at(timed_points, when_local, offset_min=0, tolerance_s=PHOTO_TRACK_TOLERANCE_S):
    """Position auf dem Track zur Aufnahmezeit, zwischen den Nachbarpunkten interpoliert.
    when_local = naive Ortszeit Europe/Berlin (so liefert EXIF sie); offset_min gleicht eine
    falsch gehende Kamera-Uhr aus (+5 = Kamera geht 5 Minuten vor). Liefert (lat, lng) oder None,
    wenn die Zeit mehr als tolerance_s vor dem Start / nach dem Ende der Aufzeichnung liegt."""
    if not timed_points or when_local is None:
        return None
    try:
        from zoneinfo import ZoneInfo
        ts = when_local.replace(tzinfo=ZoneInfo('Europe/Berlin')).timestamp() - (offset_min or 0) * 60
    except Exception:
        return None
    first, last = timed_points[0], timed_points[-1]
    if ts < first[0] - tolerance_s or ts > last[0] + tolerance_s:
        return None
    if ts <= first[0]:
        return round(first[1], 6), round(first[2], 6)
    if ts >= last[0]:
        return round(last[1], 6), round(last[2], 6)
    import bisect
    i = bisect.bisect_left(timed_points, (ts,))      # erster Punkt mit Zeit >= ts (i >= 1, da ts > first)
    a, b = timed_points[i - 1], timed_points[i]
    span = b[0] - a[0]
    if span <= 0:
        frac = 0.0
    elif span > PHOTO_TRACK_GAP_S:                    # Lücke: näher liegenden Punkt nehmen
        frac = 0.0 if (ts - a[0]) <= (b[0] - ts) else 1.0
    else:
        frac = (ts - a[0]) / span
    return (round(a[1] + (b[1] - a[1]) * frac, 6),
            round(a[2] + (b[2] - a[2]) * frac, 6))


def _place_photos_on_track(photos, timed_points, offset_min=0):
    """Fotos ohne Position (oder mit bereits geschätzter Position) anhand ihrer Aufnahmezeit auf
    den Track setzen. Liefert (platziert, ohne_zeit, ausserhalb). Commit macht der Aufrufer."""
    placed = no_time = outside = 0
    for p in photos:
        if p.has_gps and p.gps_source != 'track':
            continue
        if not p.taken_at:
            no_time += 1
            continue
        pos = _track_position_at(timed_points, p.taken_at, offset_min)
        if pos:
            p.lat, p.lng, p.gps_source = pos[0], pos[1], 'track'
            placed += 1
        else:
            outside += 1
    return placed, no_time, outside


GASTRO_NEAR_M = 150   # Build j: Einkehr gilt als "an der Route", wenn sie höchstens so viele Meter neben dem Track liegt


def gastro_near_track(points, max_m=GASTRO_NEAR_M, limit=12):
    """Build j: Gastro-Einträge, die höchstens max_m Meter neben dem Track liegen.
    Liefert nach Streckenkilometer sortierte dicts: name, spot_type, type_label, lat, lng,
    dist_m (Abstand zum Track), km (Streckenkilometer), frac (Anteil der Strecke 0..1, ab
    dem der Punkt erreicht ist – für die Karten-Animation). Fehler → []."""
    import math
    if not points or len(points) < 2:
        return []
    try:
        step = max(1, len(points) // 4000)        # Rechenzeit begrenzen, Auflösung bleibt fein genug
        pts = points[::step]
        if step > 1 and (len(points) - 1) % step:
            pts.append(points[-1])
        lats = [pt['lat'] for pt in pts]; lngs = [pt['lng'] for pt in pts]
        mid_lat = (min(lats) + max(lats)) / 2
        m_lat = 111320.0                                        # Meter je Grad Breite
        m_lng = 111320.0 * max(0.2, math.cos(math.radians(mid_lat)))  # Meter je Grad Länge
        d_lat, d_lng = max_m / m_lat, max_m / m_lng
        cands = GastroSpot.query.filter(
            GastroSpot.lat >= min(lats) - d_lat, GastroSpot.lat <= max(lats) + d_lat,
            GastroSpot.lng >= min(lngs) - d_lng, GastroSpot.lng <= max(lngs) + d_lng,
        ).all()
        if not cands:
            return []
        cum = [0.0]                                             # Kilometerstand je Trackpunkt
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.hypot((b['lat'] - a['lat']) * m_lat, (b['lng'] - a['lng']) * m_lng))
        labels = {'cafe': 'Café', 'kneipe': 'Kneipe/Gasthaus', 'baeckerei': 'Bäckerei',
                  'restaurant': 'Restaurant', 'imbiss': 'Imbiss', 'other': 'Einkehr'}
        found = []
        for sp in cands:
            best_d, best_i = 1e12, 0
            for i, pt in enumerate(pts):
                d = math.hypot((pt['lat'] - sp.lat) * m_lat, (pt['lng'] - sp.lng) * m_lng)
                if d < best_d:
                    best_d, best_i = d, i
            if best_d <= max_m:
                li = lunch_info(sp)                                                   # Build z
                found.append({'id': sp.id, 'name': sp.name, 'spot_type': sp.spot_type,
                              'type_label': labels.get(sp.spot_type, 'Einkehr'),
                              'lat': sp.lat, 'lng': sp.lng, 'dist_m': int(round(best_d)),
                              'km': round(cum[best_i] / 1000, 1),
                              'frac': best_i / max(1, len(pts) - 1),
                              'opens_at': sp.opens_at or '', 'hours': hours_de(getattr(sp, 'hours_text', None)),
                              'closed_days': closed_days(getattr(sp, 'hours_text', None)),   # Build t
                              'lunch_status': li['status'], 'lunch_label': li['label']})
        found.sort(key=lambda x: (x['km'], x['name']))
        return found[:limit]
    except Exception as e:
        app.logger.warning(f'gastro_near_track: {e}')
        return []


def _logo_auto_alpha(img, max_px=400):
    """Build m: Logos ohne echte Transparenz (JPEG oder PNG ohne Alphakanal, z. B. rundes Logo
    auf schwarzem/weißem Grund) bekommen eine: Der einfarbige Hintergrund wird von den vier Ecken
    aus per Flood-Fill (mit Toleranz für JPEG-Artefakte) freigestellt – innenliegende Flächen in
    derselben Farbe bleiben erhalten. Logos mit vorhandener Transparenz oder ohne einheitliche
    Eckfarbe werden unverändert (als RGBA) zurückgegeben."""
    try:
        from PIL import Image as _I, ImageDraw as _D, ImageChops as _C, ImageFilter as _F
        rgba = img.convert('RGBA')
        if max(rgba.size) > max_px:
            rgba.thumbnail((max_px, max_px), _I.LANCZOS)
        if rgba.getchannel('A').getextrema()[0] < 250:
            return rgba                                   # hat schon Transparenz
        rgb = rgba.convert('RGB')
        w, h = rgb.size
        corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
        ref = rgb.getpixel(corners[0])
        if any(sum(abs(rgb.getpixel(c)[i] - ref[i]) for i in range(3)) > 60 for c in corners):
            return rgba                                   # kein einheitlicher Hintergrund
        sentinel = (255, 0, 255) if sum(abs(ref[i] - (255, 0, 255)[i]) for i in range(3)) > 150 else (0, 255, 0)
        tmp = rgb.copy()
        for c in corners:
            _D.floodfill(tmp, c, sentinel, thresh=70)
        bg_mask = _C.difference(tmp, _I.new('RGB', tmp.size, sentinel)).convert('L').point(lambda v: 255 if v == 0 else 0)
        alpha = _C.invert(bg_mask).filter(_F.GaussianBlur(0.6))   # Kante leicht weich
        if alpha.getextrema()[0] == 255:
            return rgba                                   # nichts freigestellt
        rgba.putalpha(alpha)
        return rgba
    except Exception as e:
        app.logger.warning(f'_logo_auto_alpha: {e}')
        try:
            return img.convert('RGBA')
        except Exception:
            return None


def _tour_day_weather(tour, lat=None, lng=None):
    """Tageswetter am Treffpunkt für den Tourtag (Open-Meteo) → dict oder None.
    Voraussetzungen: festes Datum, Ortskoordinaten (Treffpunkt oder lat/lng als Ersatz, z. B.
    GPX-Start) und der Server muss api.open-meteo.com erreichen. Build j: Für Touren, die länger
    als ~3 Monate zurückliegen, antwortet nur noch das Archiv (archive-api) – daher zwei Versuche
    in passender Reihenfolge. 'kind' = Symbolart für die gezeichneten Wettersymbole der Server-
    Folie, 'icon' = Emoji für die Browser-Vorschau.
    Build q: zusätzlich label (Klartext), rain_mm, wind_kmh, wind_dir, sun_h; das Ergebnis wird
    für vergangene Tage in tours.weather_json gecacht (Wetter von gestern ändert sich nicht mehr)
    – Video-Seite, Rendering und Wetter-Rückblick brauchen dann keinen API-Aufruf mehr."""
    if not (tour.tour_date and not tour.is_date_open):
        return None
    if tour.meeting_lat and tour.meeting_lng:
        lat, lng = tour.meeting_lat, tour.meeting_lng
    if not (lat and lng):
        return None
    try:
        age_days = (date.today() - tour.tour_date).days
    except Exception:
        age_days = 0
    cache_key = f'{tour.tour_date.isoformat()}|{round(float(lat), 3)}|{round(float(lng), 3)}'
    try:
        cached = json.loads(getattr(tour, 'weather_json', None) or '{}')
        if cached.get('key') == cache_key and (cached.get('data') or {}).get('temp_max') is not None:
            return cached['data']
    except Exception:
        pass
    urls = ['https://api.open-meteo.com/v1/forecast', 'https://archive-api.open-meteo.com/v1/archive']
    if age_days > 80:
        urls.reverse()
    icon_map = {0: '☀️', 1: '🌤️', 2: '🌤️', 3: '☁️', 45: '🌫️', 48: '🌫️',
                51: '🌦️', 53: '🌦️', 55: '🌦️', 61: '🌧️', 63: '🌧️', 65: '🌧️',
                71: '🌨️', 73: '🌨️', 75: '🌨️', 80: '🌦️', 81: '🌧️', 82: '⛈️',
                95: '⛈️', 96: '⛈️', 99: '⛈️'}

    def _label(c):
        if c is None:  return ''
        if c == 0:     return 'Sonnig'
        if c <= 2:     return 'Überwiegend sonnig'
        if c == 3:     return 'Bewölkt'
        if c <= 49:    return 'Nebel / Dunst'
        if c <= 57:    return 'Nieselregen'
        if c <= 67:    return 'Regen'
        if c <= 77:    return 'Schnee'
        if c <= 82:    return 'Regenschauer'
        if c <= 86:    return 'Schneeschauer'
        return 'Gewitter'

    daily_full = ('weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,'
                  'windspeed_10m_max,winddirection_10m_dominant,sunshine_duration')
    daily_basic = 'weathercode,temperature_2m_max,temperature_2m_min'
    result = None
    for url in urls:
        for daily in (daily_full, daily_basic):      # erst mit Zusatzwerten, zur Not nur das Nötigste
            try:
                resp = http_requests.get(url, params={
                    'latitude': lat, 'longitude': lng, 'daily': daily,
                    'timezone': 'Europe/Berlin',
                    'start_date': tour.tour_date.isoformat(), 'end_date': tour.tour_date.isoformat()},
                    timeout=5)
                d = resp.json().get('daily', {}) or {}

                def _first(key):
                    v = d.get(key) or [None]
                    return v[0] if v else None
                tmax = _first('temperature_2m_max')
                if tmax is None:
                    continue
                tmin = _first('temperature_2m_min')
                wc = _first('weathercode')
                if wc == 0:                            kind = 'sun'
                elif wc in (1, 2):                     kind = 'partly'
                elif wc == 3:                          kind = 'cloud'
                elif wc in (45, 48):                   kind = 'fog'
                elif wc in (71, 73, 75, 77, 85, 86):   kind = 'snow'
                elif wc in (95, 96, 99):               kind = 'storm'
                elif wc is not None and wc >= 51:      kind = 'rain'
                else:                                  kind = 'thermo'
                rain = _first('precipitation_sum'); wind = _first('windspeed_10m_max')
                wdeg = _first('winddirection_10m_dominant'); sun = _first('sunshine_duration')
                result = {'temp_max': round(tmax), 'temp_min': round(tmin if tmin is not None else tmax),
                          'icon': icon_map.get(wc, '🌡️'), 'kind': kind, 'code': wc, 'label': _label(wc),
                          'rain_mm': round(float(rain), 1) if rain is not None else None,
                          'wind_kmh': int(round(float(wind))) if wind is not None else None,
                          'wind_dir': (['N', 'NO', 'O', 'SO', 'S', 'SW', 'W', 'NW'][int(round(float(wdeg) / 45)) % 8]
                                       if wdeg is not None else None),
                          'sun_h': round(float(sun) / 3600, 1) if sun is not None else None}
                break
            except Exception:
                continue
        if result:
            break
    if result is None:
        return None
    if age_days >= 1 and hasattr(tour, 'weather_json'):      # Vergangenheit: dauerhaft merken
        try:
            tour.weather_json = json.dumps({'key': cache_key, 'data': result})
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f'_tour_day_weather cache: {e}')
    return result


@app.route('/touren/<int:tour_id>/wetter-tag')
@login_required
def tour_weather_day(tour_id):
    """Build q: Wetter am Tourtag als JSON (Rückblick-Kachel auf der Detailseite, asynchron
    geladen, damit die Seite nicht auf Open-Meteo wartet). Ohne Treffpunkt gibt der Browser
    den GPX-Start als Ersatz-Ort mit (?lat=&lng=)."""
    tour = _tour_or_404(tour_id)
    try:
        lat = float(request.args.get('lat') or 0) or None
        lng = float(request.args.get('lng') or 0) or None
    except ValueError:
        lat = lng = None
    w = _tour_day_weather(tour, lat, lng)
    if not w:
        return jsonify({'error': 'Keine Wetterdaten für diesen Tag.'})
    return jsonify(w)


@app.route('/touren/<int:tour_id>')
@login_required
def tour_detail(tour_id):
    tour = _tour_or_404(tour_id)

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
            if gpx_data and tour.gpx_preview is None:      # Build w: Fahrzeit/Vorschau einmalig nachtragen
                try:
                    _tour_apply_gpx_metrics(tour, gpx_data)
                    db.session.commit()
                except Exception as _ex:
                    db.session.rollback()
                    app.logger.warning(f'GPX-Kennzahlen Tour {tour.id}: {_ex}')

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

    # Build ab: Fahrgemeinschaften (Angebote zuerst)
    from sqlalchemy.orm import joinedload as _jl
    rides = (TourRide.query.filter_by(tour_id=tour_id).options(_jl(TourRide.user))
             .order_by(TourRide.kind.asc(), TourRide.created_at.asc()).all())
    rides = [r for r in rides if r.user]
    my_ride = next((r for r in rides if r.user_id == current_user.id), None)

    # Build q: Einkehr-Orte höchstens GASTRO_NEAR_M m neben dem Track (zuschaltbare Karten-Ebene);
    # gleicher Helfer wie die Video-Folie, Track dafür auf ≤ 1500 Punkte ausgedünnt
    gastro_near = []
    if gpx_data and gpx_data.get('points'):
        _pts = gpx_data['points']
        gastro_near = gastro_near_track(_pts[::max(1, len(_pts) // 1500)], limit=20)
        for _spot in gastro_near:
            _spot['url'] = url_for('gastro_detail', spot_id=_spot['id'])

    return render_template('touren/detail.html',
                           tour=tour,
                           my_rsvp=my_rsvp,
                           attending=attending,
                           maybe=maybe,
                           declined=declined,
                           gpx_data=json.dumps(gpx_for_page(gpx_path)) if gpx_data else 'null',   # Build ab: ≤ 2000 Punkte
                           show_live=(tour.status != 'cancelled' and (tour.is_date_open or
                                      tour.tour_date >= date.today() - timedelta(days=1))),   # Build aa
                           gastro_near=gastro_near,
                           photos=photos,
                           videos=videos,
                           comments=comments,
                           all_users=all_users,
                           participant_ids=participant_ids,
                           rides=rides, my_ride=my_ride,                 # Build ab
                           gpx_timed=bool(gpx_data and gpx_data.get('moving_s')),   # Build ac: Aufzeichnung mit Zeiten?
                           gpx_span=(f"{gpx_data['start_time']}–{gpx_data['end_time']} Uhr"
                                     if gpx_data and gpx_data.get('start_time') and gpx_data.get('end_time') else ''),
                           today=date.today())


@app.route('/touren/<int:tour_id>/rsvp', methods=['POST'])
@login_required
def tour_rsvp(tour_id):
    tour   = _tour_or_404(tour_id)
    status = request.form.get('status', 'attending')
    if status not in ('attending', 'maybe', 'declined'):
        abort(400)
    if tour.is_date_open:
        flash('Anmeldung erst möglich wenn ein Termin feststeht.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id))
    if tour.status != 'planned':                       # Build ab
        flash('Die Tour ist ' + ('abgesagt' if tour.status == 'cancelled' else 'abgeschlossen')
              + ' – eine Anmeldung ist nicht mehr möglich.', 'warning')
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


@app.route('/touren/<int:tour_id>/mitfahrt', methods=['POST'])
@login_required
def tour_ride_set(tour_id):
    """Build ab: Fahrgemeinschaft anbieten (kind=offer, seats) oder suchen (kind=request) –
    ein Eintrag je Nutzer und Tour, wird beim erneuten Speichern überschrieben.
    Bei einem neuen Angebot bekommen alle Suchenden der Tour eine Push-Nachricht."""
    tour = _tour_or_404(tour_id)
    if tour.status != 'planned':
        flash('Fahrgemeinschaften nur für geplante Touren.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id) + '#fahrgemeinschaft')
    kind = request.form.get('kind', 'offer')
    if kind not in ('offer', 'request'):
        abort(400)
    seats = _parse_int(request.form.get('seats')) if kind == 'offer' else None
    if kind == 'offer' and (seats is None or seats < 1 or seats > 9):
        seats = 1
    ride = TourRide.query.filter_by(tour_id=tour_id, user_id=current_user.id).first()
    is_new_offer = kind == 'offer' and (ride is None or ride.kind != 'offer')
    if ride is None:
        ride = TourRide(tour_id=tour_id, user_id=current_user.id)
        db.session.add(ride)
    ride.kind  = kind
    ride.seats = seats
    ride.place = (request.form.get('place') or '').strip()[:120] or None
    ride.note  = (request.form.get('note') or '').strip()[:200] or None
    db.session.commit()
    if is_new_offer:
        body = f'{current_user.display_name} bietet {seats} Platz/Plätze an'
        if ride.place:
            body += f' (ab {ride.place})'
        for r in TourRide.query.filter_by(tour_id=tour_id, kind='request').all():
            if r.user_id != current_user.id and r.user:
                try:
                    send_push_to_user(r.user, title=f'🚗 Mitfahrgelegenheit: {tour.title}', body=body,
                                      url=f'/touren/{tour_id}#fahrgemeinschaft')
                except Exception as e:
                    app.logger.warning(f'ride push failed: {e}')
    flash('Fahrgemeinschaft gespeichert.' if kind == 'offer' else 'Mitfahrwunsch gespeichert.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#fahrgemeinschaft')


@app.route('/touren/<int:tour_id>/mitfahrt/loeschen', methods=['POST'])
@login_required
def tour_ride_delete(tour_id):
    """Build ab: eigenen Fahrgemeinschafts-Eintrag entfernen (Organisator/Admin: jeden per user_id)."""
    tour = _tour_or_404(tour_id)
    uid = current_user.id
    if (current_user.is_admin or current_user.is_organizer) and request.form.get('user_id'):
        uid = _parse_int(request.form.get('user_id')) or current_user.id
    TourRide.query.filter_by(tour_id=tour.id, user_id=uid).delete(synchronize_session=False)
    db.session.commit()
    flash('Eintrag entfernt.', 'info')
    return redirect(url_for('tour_detail', tour_id=tour_id) + '#fahrgemeinschaft')


@app.route('/touren/<int:tour_id>/teilnehmerliste')
@login_required
def tour_participants_print(tour_id):
    """Build ab: druckbare Teilnehmerliste mit Telefon und Notfallkontakt – nur für
    Organisatoren, Admins und den Ersteller der Tour (Datenschutz: nicht für alle sichtbar)."""
    tour = _tour_or_404(tour_id)
    if not _can_manage_tour(tour):
        abort(403)
    from sqlalchemy.orm import joinedload
    rows = (TourParticipant.query.filter(TourParticipant.tour_id == tour.id,
                                         TourParticipant.status.in_(['attending', 'maybe']))
            .options(joinedload(TourParticipant.user)).all())
    rows = [r for r in rows if r.user]
    rows.sort(key=lambda r: (0 if r.status == 'attending' else 1, (r.user.name or '').lower()))
    rides = TourRide.query.filter_by(tour_id=tour.id).options(joinedload(TourRide.user)).all()
    return render_template('touren/teilnehmerliste.html', tour=tour, rows=rows, rides=rides,
                           einkehr=_tour_einkehr_text(tour), printed_at=_berlin_now())


@app.route('/touren/<int:tour_id>/gpx', methods=['POST'])
@login_required
@organizer_required
def tour_upload_gpx(tour_id):
    tour = _tour_or_404(tour_id)
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
        _tour_apply_gpx_metrics(tour, parsed)                  # Build w
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
            from PIL import Image as PILImage, ImageOps
            img = PILImage.open(path)

            # EXIF-Rotation korrigieren (transpose respektiert Orientation-Tag)
            img = ImageOps.exif_transpose(img)

            # Build f: Dateiformat beibehalten – PNG (z. B. transparente Gruppen-Logos)
            # bleibt PNG, WebP bleibt WebP; alles andere wird als JPEG gespeichert.
            ext = os.path.splitext(path)[1].lower()
            if ext == '.png':
                fmt, save_kw = 'PNG', {'optimize': True}
                if img.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
                    img = img.convert('RGBA')
            elif ext == '.webp':
                fmt, save_kw = 'WEBP', {'quality': quality}
            else:
                fmt, save_kw = 'JPEG', {'quality': quality, 'optimize': True, 'progressive': True}

            w, h = img.size
            did_resize = max(w, h) > max_px
            if did_resize:
                ratio = max_px / max(w, h)
                new_w, new_h = int(w * ratio), int(h * ratio)
                img = img.resize((new_w, new_h), PILImage.LANCZOS)

            if fmt == 'JPEG' and img.mode != 'RGB':
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    # Transparenz auf Weiß legen (convert('RGB') allein ergäbe Schwarz)
                    rgba = img.convert('RGBA')
                    bg = PILImage.new('RGB', rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[-1])
                    img = bg
                else:
                    img = img.convert('RGB')

            # Auch ohne Verkleinern speichern, um die EXIF-Rotation zu fixieren
            img.save(path, format=fmt, **save_kw)
            if did_resize:
                app.logger.info(f'Pillow resized: {w}x{h} → {new_w}x{new_h}')
            return did_resize
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
    _photo_tour_or_404(photo)   # Audit 1.4.0: nur Fotos der eigenen Gruppe
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
        _t = url_for('tour_detail', tour_id=tour_id) + '#fotos'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'redirect': _t})
        return redirect(_t)

    tour   = _tour_or_404(tour_id)
    files  = request.files.getlist('photos')
    os.makedirs(app.config['UPLOAD_FOLDER_PHOTOS'], exist_ok=True)
    count     = 0
    gps_count = 0
    skipped   = 0
    resized   = 0
    zip_count = 0
    dupes     = 0
    placed    = 0          # Build ac: per Aufnahmezeit auf dem Track platziert
    import hashlib as _hashlib
    seen_hashes = {h for (h,) in db.session.query(TourPhoto.orig_hash)
                   .filter(TourPhoto.tour_id == tour_id, TourPhoto.orig_hash.isnot(None)).all()}
    _timed_cache = []      # Zeitstempel-Punkte des GPX, erst beim ersten Foto ohne GPS geladen

    def _timed():
        if not _timed_cache:
            _timed_cache.append(_tour_timed_points(tour))
        return _timed_cache[0]

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
        nonlocal count, gps_count, resized, dupes, placed
        ext = original_name.rsplit('.', 1)[-1].lower()
        if ext not in app.config['ALLOWED_PHOTO_EXTENSIONS']:
            return None
        if not _check_magic(data):
            app.logger.warning(f'Rejected upload with invalid magic bytes: {original_name}')
            return None
        # Duplikat-Schutz: identisches Original in dieser Tour schon vorhanden?
        h = _hashlib.sha256(data).hexdigest()
        if h in seen_hashes:
            dupes += 1
            return None
        seen_hashes.add(h)
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
        gps_source = 'exif' if (lat is not None and lng is not None) else None   # Build ac
        if lat is None or lng is None:
            try:
                c_lat = request.form.get(f'gps_lat_{idx_key}', '').strip()
                c_lng = request.form.get(f'gps_lng_{idx_key}', '').strip()
                if c_lat and c_lng:
                    clat, clng = float(c_lat), float(c_lng)
                    if -90 <= clat <= 90 and -180 <= clng <= 180 and not (clat == 0 and clng == 0):
                        lat, lng = clat, clng
                        gps_source = ('device' if request.form.get(f'gps_src_{idx_key}') == 'device'
                                      else 'exif')
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
        # Build ac: kein Standort, aber Aufnahmezeit → Position auf dem GPX-Track schätzen
        if gps_source is None and taken_at is not None:
            pos = _track_position_at(_timed(), taken_at)
            if pos:
                lat, lng = pos
                gps_source = 'track'
                placed += 1
        if gps_source in ('exif', 'device'):
            gps_count += 1
        count += 1
        return TourPhoto(
            tour_id  = tour_id,
            user_id  = current_user.id,
            filename = filename,
            caption  = request.form.get('caption', '').strip() or None,
            lat=lat, lng=lng, taken_at=taken_at, orig_hash=h,
            gps_source=gps_source,
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
    if placed:
        parts.append(f'📍 {placed} anhand der Aufnahmezeit auf der Strecke platziert (geschätzt)')
    if resized:
        parts.append(f'📐 {resized} verkleinert')
    if dupes:
        parts.append(f'♻️ {dupes} Duplikat(e) ignoriert')
    if skipped:
        parts.append(f'{skipped} übersprungen')
    flash(' – '.join(parts), 'success' if count else 'warning')

    # Build ac: Hinweis, wenn Fotos ohne Standort geblieben sind – und warum
    no_gps = count - gps_count - placed
    if count and no_gps > 0:
        tip = (f'{no_gps} Foto(s) ohne Standort. Tipp fürs Handy: Fotos über die App „Dateien“ '
               f'(Ordner DCIM/Camera) auswählen statt über die Galerie – die Galerie entfernt den '
               f'Standort beim Hochladen. ')
        if _timed():
            tip += ('Fotos mit Aufnahmezeit werden automatisch auf der Strecke platziert; diese hatten '
                    'keine Aufnahmezeit oder liegen außerhalb der Aufzeichnung – Position per ✏️ am Foto '
                    'auf der Karte setzen.')
        elif tour.gpx_file:
            tip += ('Der GPX-Track dieser Tour hat keine Zeitstempel (geplante Route) – mit einer '
                    'Aufzeichnung würden Fotos automatisch per Uhrzeit platziert. Sonst: Position per '
                    '✏️ am Foto auf der Karte setzen.')
        else:
            tip += 'Position per ✏️ am Foto auf der Karte setzen.'
        flash(tip, 'info')
    target = url_for('tour_detail', tour_id=tour_id) + '#fotos'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'redirect': target, 'count': count, 'dupes': dupes,
                        'placed': placed, 'no_gps': max(no_gps, 0)})
    return redirect(target)


@app.route('/touren/<int:tour_id>/teilnehmer/hinzufuegen', methods=['POST'])
@login_required
@organizer_required
def tour_add_participant(tour_id):
    tour = _tour_or_404(tour_id)
    user_id = request.form.get('user_id', type=int)
    if not user_id:
        flash('Bitte einen Nutzer auswählen.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id))
    user = _own_group_or_404(User.query.get_or_404(user_id))   # Audit 1.4.0
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
    _tour_or_404(tour_id)   # Audit 1.4.0: nur Touren der eigenen Gruppe
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
    tour = _tour_or_404(tour_id)
    tour.status = 'completed'
    db.session.commit()
    flash('Tour als abgeschlossen markiert und im Archiv gespeichert.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour_id))


@app.route('/touren/<int:tour_id>/bestaetigen', methods=['POST'])
@login_required
@organizer_required
def tour_confirm_participants(tour_id):
    """After tour: set confirmed_present for checked participants."""
    tour = _tour_or_404(tour_id)
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
    tour = _tour_or_404(tour_id)
    if not (current_user.is_admin or current_user.is_organizer or
            tour.created_by == current_user.id):
        abort(403)
    if request.method == 'POST':
        # Audit 1.4.0: leerer Titel / ungültiges Datum → Hinweis statt leerer Tour bzw. 500
        new_title     = request.form.get('title', '').strip()
        tour_date_str = request.form.get('tour_date', '').strip()
        parsed_date   = _parse_date(tour_date_str)
        if not new_title or (tour_date_str and parsed_date is None):
            flash('Bitte Titel und ein gültiges Datum angeben.', 'danger')
            return redirect(url_for('tour_edit', tour_id=tour.id))
        before = _tour_change_snapshot(tour)           # Build ab: für „Änderung mitteilen“
        tour.title        = new_title
        tour.description  = request.form.get('description', '').strip() or None
        tour.tour_date    = parsed_date if parsed_date else date(9999, 12, 31)
        tour.start_time   = request.form.get('start_time', '').strip() or None
        tour.difficulty   = request.form.get('difficulty', 'mittel')
        tour.approx_km    = _parse_float(request.form.get('approx_km'))
        tour.external_link = _clean_url(request.form.get('external_link'))
        tour.meeting_desc = request.form.get('meeting_desc', '').strip() or None
        tour.meeting_lat  = _parse_float(request.form.get('meeting_lat'))
        tour.meeting_lng  = _parse_float(request.form.get('meeting_lng'))
        _apply_einkehr_form(tour)                      # Build x: geplante Einkehr
        if current_user.is_admin:
            new_status = request.form.get('status', tour.status)
            if new_status in ('planned', 'completed', 'cancelled'):   # Build ab: Whitelist
                tour.status = new_status
                if new_status != 'cancelled':
                    tour.cancel_reason = None
        db.session.commit()
        flash('Tour aktualisiert.', 'success')
        if request.form.get('notify_changes'):         # Build ab
            changes = _tour_changes(before, _tour_change_snapshot(tour))
            if changes and tour.status == 'planned':
                n = _notify_tour_change(tour, changes)
                flash(f'Änderung mitgeteilt ({", ".join(c[0] for c in changes)}): '
                      f'{n} Push-Nachricht(en) + Telegram.', 'info')
            elif not changes:
                flash('Keine mitteilenswerte Änderung (Datum, Uhrzeit, Treffpunkt, Titel) – nichts verschickt.', 'info')
        return redirect(url_for('tour_detail', tour_id=tour.id))
    return render_template('touren/edit.html', tour=tour,
                           difficulties=Config.DIFFICULTY_CHOICES,
                           today=date.today())


@app.route('/touren/<int:tour_id>/loeschen', methods=['POST'])
@login_required
def tour_delete(tour_id):
    tour = _tour_or_404(tour_id)
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
    _delete_tour_dependents(tour_id)   # Audit 1.4.0: keine verwaisten Datensätze
    db.session.delete(tour)
    db.session.commit()
    flash(f'Tour „{title}" wurde gelöscht.', 'success')
    return redirect(url_for('tour_list'))


def _tour_change_snapshot(tour):
    """Build ab: die Felder, über deren Änderung Teilnehmer informiert werden."""
    return {
        'Titel':      tour.title or '',
        'Datum':      ('offen' if tour.is_date_open else tour.tour_date.strftime('%d.%m.%Y')),
        'Uhrzeit':    tour.start_time or '–',
        'Treffpunkt': tour.meeting_desc or '–',
    }


def _tour_changes(before, after):
    """Build ab: [(Feld, alt, neu), …] für alle geänderten Felder."""
    return [(k, before[k], after[k]) for k in before if before[k] != after.get(k)]


def _tour_notify_targets(tour, include_maybe=True, exclude_user_id=None):
    """Build ab: Nutzer, die zu einer Tour benachrichtigt werden (Dabei + ggf. Vielleicht)."""
    states = ['attending', 'maybe'] if include_maybe else ['attending']
    ids = {p.user_id for p in TourParticipant.query.filter(
        TourParticipant.tour_id == tour.id, TourParticipant.status.in_(states)).all()}
    ids.discard(exclude_user_id)
    return User.query.filter(User.id.in_(ids), User.is_active == True).all() if ids else []   # noqa: E712


def _notify_tour_change(tour, changes):
    """Build ab: Push an Zugesagte/Unentschlossene + Telegram, wenn Datum/Uhrzeit/Treffpunkt/Titel
    einer geplanten Tour geändert wurden. Liefert die Zahl der Push-Nachrichten."""
    lines = [f'{k}: {old} → {new}' for k, old, new in changes]
    sent = 0
    try:
        tg = (f'✏️ <b>Tour geändert: {_tg(tour.title)}</b>\n\n'
              + '\n'.join(_tg(l) for l in lines)
              + f'\n\n👉 {app.config["BASE_URL"]}/touren/{tour.id}')
        send_telegram(tg)
    except Exception as e:
        app.logger.warning(f'Telegram tour change failed: {e}')
    body = ' · '.join(lines)
    for u in _tour_notify_targets(tour, exclude_user_id=current_user.id):
        try:
            n, _ = send_push_to_user(u, title=f'✏️ Geändert: {tour.title}', body=body[:180],
                                     url=f'/touren/{tour.id}')
            sent += n
        except Exception as e:
            app.logger.warning(f'Push tour change failed for user {u.id}: {e}')
    return sent


@app.route('/touren/<int:tour_id>/absagen', methods=['POST'])
@login_required
def tour_cancel(tour_id):
    """Build ab: Tour absagen (Organisator, Admin oder Ersteller) – mit optionalem Grund;
    Zugesagte und Unentschlossene bekommen Push, die Gruppe eine Telegram-Nachricht."""
    tour = _tour_or_404(tour_id)
    if not _can_manage_tour(tour):
        abort(403)
    if tour.status == 'cancelled':
        flash('Die Tour ist bereits abgesagt.', 'info')
        return redirect(url_for('tour_detail', tour_id=tour.id))
    if tour.status == 'completed':
        flash('Eine abgeschlossene Tour kann nicht mehr abgesagt werden.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour.id))
    reason = (request.form.get('reason') or '').strip()[:200] or None
    tour.status = 'cancelled'
    tour.cancel_reason = reason
    db.session.commit()

    datum = 'Datum offen' if tour.is_date_open else tour.tour_date.strftime('%d.%m.%Y')
    sent = 0
    try:
        tg = (f'❌ <b>Tour abgesagt: {_tg(tour.title)}</b>\n\n'
              f'📅 {datum}{" um " + _tg(tour.start_time) + " Uhr" if tour.start_time else ""}\n')
        if reason:
            tg += f'📝 Grund: {_tg(reason)}\n'
        tg += f'\n👉 {app.config["BASE_URL"]}/touren/{tour.id}'
        send_telegram(tg)
    except Exception as e:
        app.logger.warning(f'Telegram cancel failed: {e}')
    body = f'{tour.title} · {datum}' + (f' · Grund: {reason}' if reason else '')
    for u in _tour_notify_targets(tour, exclude_user_id=current_user.id):
        try:
            n, _ = send_push_to_user(u, title='❌ Tour abgesagt', body=body[:180], url=f'/touren/{tour.id}')
            sent += n
        except Exception as e:
            app.logger.warning(f'Push cancel failed for user {u.id}: {e}')
    flash(f'Tour abgesagt. {sent} Push-Nachricht(en) verschickt, Telegram informiert.', 'warning')
    return redirect(url_for('tour_detail', tour_id=tour.id))


@app.route('/touren/<int:tour_id>/reaktivieren', methods=['POST'])
@login_required
def tour_uncancel(tour_id):
    """Build ab: Absage zurücknehmen – Tour ist wieder geplant, Teilnehmer werden informiert."""
    tour = _tour_or_404(tour_id)
    if not _can_manage_tour(tour):
        abort(403)
    if tour.status != 'cancelled':
        flash('Die Tour ist nicht abgesagt.', 'info')
        return redirect(url_for('tour_detail', tour_id=tour.id))
    tour.status = 'planned'
    tour.cancel_reason = None
    db.session.commit()
    datum = 'Datum offen' if tour.is_date_open else tour.tour_date.strftime('%d.%m.%Y')
    sent = 0
    try:
        send_telegram(f'✅ <b>Tour findet doch statt: {_tg(tour.title)}</b>\n\n📅 {datum}'
                      f'{" um " + _tg(tour.start_time) + " Uhr" if tour.start_time else ""}'
                      f'\n\n👉 {app.config["BASE_URL"]}/touren/{tour.id}')
    except Exception as e:
        app.logger.warning(f'Telegram uncancel failed: {e}')
    for u in _tour_notify_targets(tour, exclude_user_id=current_user.id):
        try:
            n, _ = send_push_to_user(u, title='✅ Tour findet statt', body=f'{tour.title} · {datum}',
                                     url=f'/touren/{tour.id}')
            sent += n
        except Exception as e:
            app.logger.warning(f'Push uncancel failed for user {u.id}: {e}')
    flash(f'Absage zurückgenommen – die Tour ist wieder geplant. {sent} Push-Nachricht(en) verschickt.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour.id))


def _delete_tour_dependents(tour_id):
    """Löscht Datensätze ohne DB-Cascade, die sonst als Waisen zurückbleiben
    (Videos, Kommentare, Zeitabstimmung, Bewertungen, Live-Standorte, Fahrgemeinschaften).
    Teilnehmer und Fotos räumt SQLAlchemy über die Relationship-Cascade ab."""
    for model in (TourVideo, TourComment, TimeVote, RouteRating, LiveLocation, TourRide):
        try:
            model.query.filter_by(tour_id=tour_id).delete(synchronize_session=False)
        except Exception as e:
            app.logger.warning(f'tour_delete cleanup {model.__name__}: {e}')


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
    _tour_or_404(tour_id)
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
    tour   = _tour_or_404(tour_id)
    photos = tour.photos.order_by(
        db.text('COALESCE(sort_order, 999999) ASC'), TourPhoto.taken_at.asc().nullslast(), TourPhoto.created_at.asc()
    ).all()
    gpx_data = None
    if tour.gpx_file:
        gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
        if os.path.exists(gpx_path):
            gpx_data = gpx_for_page(gpx_path)          # Build ab: ≤ 2000 Punkte im Seiten-JSON

    attending_count = TourParticipant.query.filter_by(
        tour_id=tour_id, status='attending'
    ).count()
    attending_names = [p.user.display_name for p in
                       TourParticipant.query.filter_by(tour_id=tour_id, status='attending')
                       .join(User).order_by(User.name).limit(12).all()]

    weather = _tour_day_weather(tour)   # Build j: gemeinsamer Helfer (Prognose + Archiv)

    from flask import g as _g
    default_music_url = None
    grp = getattr(_g, 'group', None)
    if grp and grp.default_music:
        default_music_url = url_for('static', filename='uploads/group_music/' + grp.default_music)

    _base_url = app.config.get('BASE_URL', '') or ''
    base_domain = _base_url.replace('https://', '').replace('http://', '').rstrip('/')
    if base_domain == 'localhost:5000':
        base_domain = ''  # lokale Entwicklung – kein sinnvoller öffentlicher Hinweis

    return render_template('touren/video.html',
                           tour=tour, photos=photos,
                           attending_count=attending_count,
                           attending_names=attending_names,
                           weather=weather,
                           default_music_url=default_music_url,
                           base_domain=base_domain,
                           gpx_data=json.dumps(gpx_data) if gpx_data else 'null')



@app.route('/touren/<int:tour_id>/video/render', methods=['POST'])
@login_required
def tour_video_render(tour_id):
    """Server-side MP4 via FFmpeg."""
    import subprocess, tempfile, shutil

    tour   = _tour_or_404(tour_id)
    photos = tour.photos.order_by(
        db.text('COALESCE(sort_order, 999999) ASC'), TourPhoto.taken_at.asc().nullslast(), TourPhoto.created_at.asc()
    ).all()

    if not photos:
        flash('Keine Fotos – Video benötigt mindestens ein Foto.', 'warning')
        return redirect(url_for('tour_video', tour_id=tour_id))

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

    # Build ab: pro Tour nur ein Rendern gleichzeitig – ein zweiter Klick (oder ein zweiter
    # Browser-Tab) würde sonst einen weiteren ffmpeg-Lauf auf demselben Shared Hosting starten.
    lock_dir = app.config['UPLOAD_FOLDER_VIDEOS']
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, f'.render_{tour_id}.lock')
    try:
        if os.path.exists(lock_path) and (_time.time() - os.path.getmtime(lock_path)) > 900:
            os.remove(lock_path)                        # verwaiste Sperre (> 15 min) aufräumen
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(lock_fd)
    except FileExistsError:
        flash('Für diese Tour wird gerade ein Video erstellt – bitte einen Moment warten und dann die Seite neu laden.', 'warning')
        return redirect(url_for('tour_video', tour_id=tour_id))
    except OSError as e:
        app.logger.warning(f'Video-Sperre {lock_path}: {e}')

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
        if not music_path:
            # Fallback: Standardmusik der Gruppe verwenden, falls gesetzt
            from flask import g as _g
            grp = getattr(_g, 'group', None)
            if grp and grp.default_music:
                default_src = os.path.join(app.root_path, 'static', 'uploads', 'group_music', grp.default_music)
                if os.path.exists(default_src):
                    ext = grp.default_music.rsplit('.', 1)[-1].lower()
                    music_path = os.path.join(tmpdir, f'music.{ext}')
                    import shutil as _sh2
                    _sh2.copy2(default_src, music_path)

        photo_dur  = int(request.form.get('photo_duration', 5))
        fps        = 25
        fmt        = request.form.get('video_format', 'reels')
        # Plattform-Presets – Auflösung + "Safe Area" (Rand ohne Foto, für Titel/Untertitel-Bereich)
        FORMAT_PRESETS = {
            'reels':     (1080, 1920, 40),   # Instagram/TikTok Reels, Stories, WhatsApp Status
            'shorts':    (1080, 1920, 40),   # YouTube Shorts – gleiche Maße wie Reels
            'feed':      (1080, 1350, 36),   # Instagram/Facebook Feed-Post 4:5
            'square':    (1080, 1080, 32),   # Facebook/Instagram quadratisch 1:1
            'landscape': (1920, 1080, 30),   # YouTube/TV/Desktop 16:9
        }
        W, H, SAFE = FORMAT_PRESETS.get(fmt, FORMAT_PRESETS['reels'])
        INNER_H    = H - 2 * SAFE

        # ── Jedes Foto vorbereiten (Pillow) ───────────────────────────────────
        # Portrait  → contain auf W×INNER_H, Safe-Area-Padding
        # Landscape → Blur-BG (W×H) + contain FG overlay
        try:
            from PIL import (Image as _PIL, ImageFilter as _ILF,
                             ImageFont as _IFO, ImageDraw as _ID_MOD)
            PIL_OK = True
        except Exception:
            PIL_OK = False

        def build_photo_canvas(src_path):
            """Erstellt das fertige W×H-Vollbild (Contain/Blur-BG) und gibt das PIL-Image zurück,
            OHNE es zu speichern. None bei Fehler."""
            if not PIL_OK:
                return None
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
                return canvas
            except Exception as e:
                app.logger.warning(f'build_photo_canvas error: {e}', exc_info=True)
                return None

        def make_frame(src_path, dst_path, overlay_png=None):
            """Erstellt ein einzelnes fertig skaliertes W×H JPEG (Fallback ohne Ken-Burns-Effekt)."""
            canvas = build_photo_canvas(src_path)
            if canvas is None:
                import shutil as _sh; _sh.copy2(src_path, dst_path); return
            if overlay_png and os.path.exists(overlay_png):
                try:
                    ov = _PIL.open(overlay_png).convert('RGBA')
                    canvas = _PIL.alpha_composite(canvas.convert('RGBA'), ov).convert('RGB')
                except Exception:
                    pass
            canvas.save(dst_path, 'JPEG', quality=92)

        FADE_IN, FADE_OUT = 0.25, 0.35   # Build i: weiche Übergänge (kurzer Dip nach Schwarz)

        def _fade_vf(duration):
            """ffmpeg-Filter: Ein-/Ausblenden eines Segments der Länge duration."""
            return (f'fade=t=in:st=0:d={FADE_IN},'
                    f'fade=t=out:st={max(0.0, round(duration - FADE_OUT, 3))}:d={FADE_OUT}')

        def image_to_segment(img_path, out_path, duration):
            """Wandelt ein einzelnes Standbild in ein kurzes, stilles Video-Segment um.
            Damit besteht die finale Concat-Liste NUR aus einheitlichen Video-Clips
            (kein Mischen von Bild+Dauer-Eintraegen und echten .mp4-Segmenten mehr,
            was je nach FFmpeg-Version zu fehlenden/uebersprungenen Eintraegen fuehren kann)."""
            if not ffmpeg_bin:
                return False
            try:
                n_frames = max(2, int(round(duration * fps)))
                cmd = [
                    ffmpeg_bin, '-y', '-loop', '1', '-i', img_path,
                    '-t', str(duration),
                    '-r', str(fps),
                    '-vf', f'scale={W}:{H},{_fade_vf(duration)}',
                    '-frames:v', str(n_frames),
                    '-pix_fmt', 'yuv420p',
                    out_path
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                return result.returncode == 0 and os.path.exists(out_path)
            except Exception as e:
                app.logger.warning(f'image_to_segment error: {e}', exc_info=True)
                return False

        def frames_to_segment(frame_duration_pairs, out_path):
            """Wandelt eine Sequenz von Einzelbildern (z.B. die Kartenanimation) in
            EIN homogenes Video-Segment um, damit die aeussere Concat-Liste
            ausschliesslich aus .mp4-Dateien besteht."""
            if not ffmpeg_bin or not frame_duration_pairs:
                return False
            try:
                inner_concat = out_path + '_inner.txt'
                with open(inner_concat, 'w') as icf:
                    for fpath, fdur in frame_duration_pairs:
                        icf.write(f"file '{fpath}'\nduration {fdur}\n")
                    # Letztes Bild laut FFmpeg-Konvention nochmal ohne duration wiederholen,
                    # sonst wird die letzte "duration"-Angabe von manchen Versionen ignoriert
                    last_path = frame_duration_pairs[-1][0]
                    icf.write(f"file '{last_path}'\n")

                total_dur = sum(d for _, d in frame_duration_pairs)
                cmd = [
                    ffmpeg_bin, '-y', '-f', 'concat', '-safe', '0', '-i', inner_concat,
                    '-r', str(fps),
                    '-vf', f'scale={W}:{H},{_fade_vf(total_dur)}',
                    '-pix_fmt', 'yuv420p',
                    out_path
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=60)
                try:
                    os.remove(inner_concat)
                except Exception:
                    pass
                return result.returncode == 0 and os.path.exists(out_path)
            except Exception as e:
                app.logger.warning(f'frames_to_segment error: {e}', exc_info=True)
                return False

        def make_photo_zoom_segment(src_path, out_path, total_dur, zoom_in=True, overlay_png=None):
            """Ken-Burns-Effekt: FLUESSIGER Zoom uebers Foto via FFmpeg zoompan-Filter
            (echte Pro-Frame-Berechnung durch FFmpeg selbst, kein sichtbares Ruckeln
            wie bei wenigen Einzelbildern). Gibt True bei Erfolg zurueck.
            Build i: Zoom um die Bildmitte (vorher Richtung linke obere Ecke), Ein-/Aus-
            blenden, und optional ein transparentes PNG (Logo, Bildunterschrift), das NACH
            dem Zoom aufgelegt wird – bleibt dadurch scharf und ortsfest."""
            canvas = build_photo_canvas(src_path)
            if canvas is None or not ffmpeg_bin:
                return False
            try:
                base_jpg = out_path + '_base.jpg'
                canvas.save(base_jpg, 'JPEG', quality=95)

                n_frames = max(2, int(round(total_dur * fps)))
                if zoom_in:
                    z_expr = f"1+0.09*on/{n_frames-1}"
                else:
                    z_expr = f"1.09-0.09*on/{n_frames-1}"

                vf = (f"scale={W*2}:{H*2},"
                      f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                      f":d={n_frames}:s={W}x{H}:fps={fps},"
                      f"{_fade_vf(total_dur)}")
                if overlay_png:
                    cmd = [
                        ffmpeg_bin, '-y', '-loop', '1', '-i', base_jpg, '-i', overlay_png,
                        '-filter_complex', f"[0:v]{vf}[v0];[v0][1:v]overlay=0:0:format=auto[v]",
                        '-map', '[v]',
                        '-frames:v', str(n_frames),
                        '-pix_fmt', 'yuv420p',
                        out_path
                    ]
                else:
                    cmd = [
                        ffmpeg_bin, '-y', '-loop', '1', '-i', base_jpg,
                        '-vf', vf,
                        '-frames:v', str(n_frames),
                        '-pix_fmt', 'yuv420p',
                        out_path
                    ]
                result = subprocess.run(cmd, capture_output=True, timeout=60)
                try:
                    os.remove(base_jpg)
                except Exception:
                    pass
                return result.returncode == 0 and os.path.exists(out_path)
            except Exception as e:
                app.logger.warning(f'make_photo_zoom_segment error: {e}', exc_info=True)
                return False

        # ── Titel-/Stats-/Outro-Folien als eigene Bilder rendern (Pillow) ──────
        # Damit landet im MP4 dieselbe "Story" wie in der Browser-Vorschau,
        # nicht nur die reine Foto-Diashow.
        def _pil_font(size, bold=True):
            candidates = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else
                '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
                '/usr/local/share/fonts/DejaVuSans-Bold.ttf' if bold else
                '/usr/local/share/fonts/DejaVuSans.ttf',
                os.path.join(os.path.dirname(__file__), 'static', 'fonts', 'DejaVuSans-Bold.ttf') if bold else
                os.path.join(os.path.dirname(__file__), 'static', 'fonts', 'DejaVuSans.ttf'),
            ]
            for path in candidates:
                if os.path.exists(path):
                    try:
                        return _IFO.truetype(path, size)
                    except Exception:
                        pass
            return _IFO.load_default()

        def _centered_text(draw, cx, y, text, font, fill, stroke_width=0, stroke_fill=None):
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw/2, y), text, font=font, fill=fill,
                      stroke_width=stroke_width, stroke_fill=stroke_fill)

        # ── Build i: Gruppenlogo, Bildunterschriften, Profilbilder ─────────────
        def _logo_scaled(max_h):
            """Gruppenlogo (RGBA) auf Höhe max_h skaliert, höchstens 28 % der Breite."""
            if logo_rgba is None:
                return None
            r = min(max_h / logo_rgba.height, (W * 0.28) / logo_rgba.width)
            size = (max(1, int(logo_rgba.width * r)), max(1, int(logo_rgba.height * r)))
            return logo_rgba.resize(size, _PIL.LANCZOS)

        def paste_watermark(canvas, corner='tr', opacity=0.85, max_h=None):
            """Logo als Wasserzeichen in eine Ecke (innerhalb der Safe-Area). canvas RGB oder RGBA."""
            lg = _logo_scaled(max_h or int(H * 0.055))
            if lg is None:
                return canvas
            if opacity < 1:
                lg.putalpha(lg.getchannel('A').point(lambda v: int(v * opacity)))
            m = SAFE + 16
            pos = {'tr': (W - m - lg.width, m), 'tl': (m, m),
                   'br': (W - m - lg.width, H - m - lg.height), 'bl': (m, H - m - lg.height)}[corner]
            if canvas.mode == 'RGBA':
                canvas.alpha_composite(lg, pos)
            else:
                canvas.paste(lg, pos, lg)
            return canvas

        def _wrap_text(draw, text, font, max_w, max_lines):
            """Text auf max_lines Zeilen umbrechen; Überhang wird mit „…“ gekürzt."""
            words, lines, cur = text.split(), [], ''
            for w_ in words:
                trial = (cur + ' ' + w_).strip()
                if draw.textlength(trial, font=font) <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(cur); cur = w_
            if cur:
                lines.append(cur)
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                last = lines[-1] + '…'
                while draw.textlength(last, font=font) > max_w and len(last) > 2:
                    last = last[:-2] + '…'
                lines[-1] = last
            return lines

        def _photo_on_mini_map(photo):
            """Build o: Foto hat plausible GPS-Daten (nahe der Track-Box) → Mini-Karte möglich."""
            mt = _mini_track
            if not mt or not (photo.lat and photo.lng):
                return False
            pad_lat = max(0.02, (mt['max_lat'] - mt['min_lat']) * 0.25)
            pad_lng = max(0.03, (mt['max_lng'] - mt['min_lng']) * 0.25)
            return (mt['min_lat'] - pad_lat <= photo.lat <= mt['max_lat'] + pad_lat and
                    mt['min_lng'] - pad_lng <= photo.lng <= mt['max_lng'] + pad_lng)

        def _draw_mini_map(layer, photo, bar_top=None):
            """Build o: Mini-Karte unten rechts auf dem Foto – Track-Umriss, bis zum Aufnahmeort
            orange, Marker am Aufnahmeort, km-Stand. Sitzt über der Unterschrift-Leiste (bar_top),
            falls es eine gibt. Rein gezeichnet (keine Kacheln) – schnell und klein gut lesbar."""
            mt = _mini_track
            side = int(min(W, H) * 0.22)
            m = SAFE + 24
            x0 = W - m - side
            y1 = (bar_top - 16) if bar_top else (H - m)
            y0 = y1 - side
            draw = _ID_MOD.Draw(layer)
            draw.rounded_rectangle([x0, y0, x0 + side, y1], radius=18, fill=(0, 0, 0, 140),
                                   outline=(255, 255, 255, 210), width=2)
            pad, label_h = 20, 24
            iw, ih = side - 2 * pad, side - 2 * pad - label_h
            lat_r = (mt['max_lat'] - mt['min_lat']) or 1e-4
            lng_r = ((mt['max_lng'] - mt['min_lng']) or 1e-4) * mt['cos']
            sc = min(iw / lng_r, ih / lat_r)
            cx, cy = x0 + side / 2, y0 + pad + ih / 2
            mid_lat = (mt['max_lat'] + mt['min_lat']) / 2
            mid_lng = (mt['max_lng'] + mt['min_lng']) / 2

            def P(lat, lng):
                return (cx + (lng - mid_lng) * mt['cos'] * sc, cy - (lat - mid_lat) * sc)

            pts = mt['pts']
            xy = [P(q['lat'], q['lng']) for q in pts]
            best_i = min(range(len(pts)),
                         key=lambda i: (pts[i]['lat'] - photo.lat) ** 2 + ((pts[i]['lng'] - photo.lng) * mt['cos']) ** 2)
            if len(xy) > 1:
                draw.line(xy, fill=(255, 255, 255, 190), width=3, joint='curve')
            if best_i >= 1:
                draw.line(xy[:best_i + 1], fill=(240, 133, 30, 255), width=4, joint='curve')
            px, py = P(photo.lat, photo.lng)
            px = min(max(px, x0 + 10), x0 + side - 10)      # Foto leicht abseits → im Kasten halten
            py = min(max(py, y0 + 10), y1 - 10)
            draw.ellipse([px - 8, py - 8, px + 8, py + 8], fill=(240, 133, 30, 255), outline=(255, 255, 255, 255), width=3)
            lbl = f"km {mt['cum_km'][best_i]:.1f}".replace('.', ',')
            f = _pil_font(18)
            draw.text((cx - draw.textlength(lbl, font=f) / 2, y1 - pad - label_h + 6), lbl, font=f, fill=(255, 255, 255, 255))

        def make_photo_overlay(photo, dst_png):
            """Transparentes W×H-PNG für ein Foto: Wasserzeichen oben rechts, unten eine
            dezente Leiste mit Uhrzeit (taken_at) und Bildunterschrift (caption), Build o:
            Mini-Karte unten rechts (Fotos mit GPS). Liefert True, wenn es etwas aufzulegen gibt."""
            caption = (photo.caption or '').strip()
            when = photo.taken_at.strftime('%H:%M Uhr') if photo.taken_at else ''
            has_map = _photo_on_mini_map(photo)
            if not (caption or when or logo_rgba is not None or has_map):
                return False
            try:
                layer = _PIL.new('RGBA', (W, H), (0, 0, 0, 0))
                draw = _ID_MOD.Draw(layer)
                bar_top = None
                if caption or when:
                    cap_font  = _pil_font(min(34, int(W / 30)))
                    time_font = _pil_font(22, bold=False)
                    pad, m = 26, SAFE + 24
                    max_w = W - 2 * m - 2 * pad
                    lines = _wrap_text(draw, caption, cap_font, max_w, 2) if caption else []
                    line_h = int(cap_font.size * 1.3)
                    bar_h = 2 * pad + (30 if when else 0) + len(lines) * line_h - (6 if (when and lines) else 0)
                    # Leiste nur so breit wie der Text (mind. 1/3 der Breite), links ausgerichtet
                    text_w = max([draw.textlength(l_, font=cap_font) for l_ in lines] +
                                 ([draw.textlength(when, font=time_font)] if when else [0]))
                    bar_w = int(min(W - 2 * m, max(W / 3, text_w + 2 * pad)))
                    y0 = H - m - bar_h
                    bar_top = y0
                    draw.rounded_rectangle([m, y0, m + bar_w, y0 + bar_h], radius=18, fill=(0, 0, 0, 150))
                    ty = y0 + pad - 4
                    if when:
                        draw.text((m + pad, ty), when, font=time_font, fill=(255, 210, 110, 255))
                        ty += 30 - (6 if lines else 0)
                    for l_ in lines:
                        draw.text((m + pad, ty), l_, font=cap_font, fill=(255, 255, 255, 255))
                        ty += line_h
                if has_map:
                    _draw_mini_map(layer, photo, bar_top)
                paste_watermark(layer, 'tr')
                layer.save(dst_png, 'PNG')
                return True
            except Exception as e:
                app.logger.warning(f'make_photo_overlay error: {e}', exc_info=True)
                return False

        def _avatar_row_layer(users_info):
            """RGBA-Streifen (Breite W) mit runden Profilbildern – ohne Bild Initialen auf
            farbigem Kreis – und Namen darunter; max. 8, Rest als „+N“."""
            if not users_info:
                return None
            try:
                from PIL import ImageOps as _IOPS
                shown = list(users_info[:8])
                extra = len(users_info) - len(shown)
                n = len(shown) + (1 if extra > 0 else 0)
                gap_f = 0.3
                size = min(int(H * 0.06), int((W - 2 * SAFE - 40) / (n + (n - 1) * gap_f)))
                gap = int(size * gap_f)
                name_font = _pil_font(max(15, int(size * 0.2)), bold=False)
                layer_h = size + 14 + int(size * 0.2) + 12
                layer = _PIL.new('RGBA', (W, layer_h), (0, 0, 0, 0))
                draw = _ID_MOD.Draw(layer)
                SS = 4   # Supersampling für glatte Kreisränder
                big = (size * SS, size * SS)
                ring = _PIL.new('RGBA', big, (0, 0, 0, 0))
                _ID_MOD.Draw(ring).ellipse((0, 0, big[0] - 1, big[1] - 1), outline=(255, 255, 255, 255), width=3 * SS)
                ring = ring.resize((size, size), _PIL.LANCZOS)
                mask = _PIL.new('L', big, 0)
                _ID_MOD.Draw(mask).ellipse((0, 0, big[0] - 1, big[1] - 1), fill=255)
                palette = [(198, 40, 40), (46, 125, 50), (21, 101, 192), (240, 133, 30),
                           (106, 27, 154), (0, 131, 143), (173, 20, 87), (84, 110, 122)]
                total_w = n * size + (n - 1) * gap
                x = (W - total_w) // 2

                def circle_with_text(text, color):
                    c = _PIL.new('RGBA', big, (0, 0, 0, 0))
                    _ID_MOD.Draw(c).ellipse((0, 0, big[0] - 1, big[1] - 1), fill=color + (255,))
                    c = c.resize((size, size), _PIL.LANCZOS)
                    f = _pil_font(int(size * 0.4))
                    d2 = _ID_MOD.Draw(c)
                    bb = d2.textbbox((0, 0), text, font=f)
                    d2.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]),
                            text, font=f, fill=(255, 255, 255, 255))
                    return c

                for idx, (name, avatar_fn) in enumerate(shown):
                    circ = None
                    if avatar_fn:
                        ap = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], avatar_fn)
                        if os.path.exists(ap):
                            try:
                                im = _IOPS.fit(_PIL.open(ap).convert('RGB'), big, _PIL.LANCZOS).convert('RGBA')
                                im.putalpha(mask)
                                circ = im.resize((size, size), _PIL.LANCZOS)
                            except Exception:
                                circ = None
                    if circ is None:
                        initials = ''.join(part[0] for part in name.split()[:2]).upper() or '?'
                        circ = circle_with_text(initials, palette[sum(map(ord, name)) % len(palette)])
                    layer.alpha_composite(circ, (x, 0))
                    layer.alpha_composite(ring, (x, 0))
                    label = name.split()[0] if name else ''
                    while draw.textlength(label, font=name_font) > size + gap - 6 and len(label) > 2:
                        label = label[:-2] + '…'
                    tw = draw.textlength(label, font=name_font)
                    draw.text((x + size / 2 - tw / 2, size + 12), label, font=name_font, fill=(230, 230, 230, 255))
                    x += size + gap
                if extra > 0:
                    layer.alpha_composite(circle_with_text(f'+{extra}', (58, 74, 108)), (x, 0))
                    layer.alpha_composite(ring, (x, 0))
                return layer
            except Exception as e:
                app.logger.warning(f'_avatar_row_layer error: {e}', exc_info=True)
                return None

        def _cover_photo_bg(canvas_size):
            """Nimmt das erste verfügbare Foto als unscharfen Vollbild-Hintergrund für Titel/Outro."""
            bg = _PIL.new('RGB', canvas_size, (30, 45, 80))
            for p in photos:
                src = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], p.filename)
                if not os.path.exists(src):
                    continue
                try:
                    img = _PIL.open(src).convert('RGB')
                    ratio_fill = max(canvas_size[0]/img.width, canvas_size[1]/img.height)
                    bw, bh = int(img.width*ratio_fill)+4, int(img.height*ratio_fill)+4
                    img = img.resize((bw, bh), _PIL.LANCZOS)
                    img = img.filter(_ILF.GaussianBlur(radius=18))
                    bx, by = (bw-canvas_size[0])//2, (bh-canvas_size[1])//2
                    bg = img.crop((bx, by, bx+canvas_size[0], by+canvas_size[1]))
                    break
                except Exception:
                    continue
            overlay = _PIL.new('RGB', canvas_size, (10, 18, 40))
            return _PIL.blend(bg, overlay, 0.45)

        def make_title_frame(dst_path):
            if not PIL_OK:
                return False
            try:
                canvas = _cover_photo_bg((W, H))
                draw = _ID_MOD.Draw(canvas)
                cx, cy = W//2, H//2
                max_w = int(W * 0.88)
                title_txt = (tour.title or '')[:120]
                t_size = min(58, int(W/13))
                while True:
                    title_font = _pil_font(t_size)
                    words, lines, cur = title_txt.split(), [], ''
                    for w_ in words:
                        trial = (cur + ' ' + w_).strip()
                        bb = draw.textbbox((0, 0), trial, font=title_font)
                        if bb[2] - bb[0] <= max_w or not cur:
                            cur = trial
                        else:
                            lines.append(cur); cur = w_
                    if cur: lines.append(cur)
                    widest = max((draw.textbbox((0, 0), l_, font=title_font)[2] for l_ in lines), default=0)
                    if (widest <= max_w and len(lines) <= 4) or t_size <= 24:
                        break
                    t_size -= 4
                line_h = int(t_size * 1.25)
                block_top = cy - 10 - (len(lines) - 1) * line_h // 2
                lg = _logo_scaled(int(H * 0.12))          # Build i: Gruppenlogo über dem Titel
                if lg is not None and block_top - lg.height - 36 > SAFE + 10:
                    canvas.paste(lg, (cx - lg.width // 2, block_top - lg.height - 36), lg)
                for li, l_ in enumerate(lines):
                    _centered_text(draw, cx, block_top + li * line_h, l_, title_font, (255,255,255),
                                  stroke_width=2, stroke_fill=(0,0,0))
                below = block_top + len(lines) * line_h - cy + 20  # Versatz für Datum/Stats
                date_font = _pil_font(30, bold=False)
                date_str = tour.tour_date.strftime('%d.%m.%Y') if (tour.tour_date and not tour.is_date_open) else ''
                if date_str:
                    _centered_text(draw, cx, cy+below+10, date_str, date_font, (230,230,230))
                if tour.gpx_km:
                    extra = f'{tour.gpx_km} km' + (f'  ·  {int(tour.gpx_ascent)} Hm' if tour.gpx_ascent else '')
                    _centered_text(draw, cx, cy+below+55, extra, _pil_font(24, bold=False), (210,210,210))
                # Build m: Wetter (gezeichnetes Symbol + Temperatur) und Teilnehmerzahl wie in der Vorschau
                bits_font = _pil_font(22, bold=False)
                bits = []
                if _weather:
                    bits.append(f"{_weather['temp_max']}°C")
                if _attending_count:
                    bits.append(f'{_attending_count} dabei')
                if bits:
                    txt = '   ·   '.join(bits)
                    ty = cy + below + (95 if tour.gpx_km else 55)
                    tw = draw.textlength(txt, font=bits_font)
                    icon_s = 30 if _weather else 0
                    gx = cx - (tw + (icon_s + 10 if icon_s else 0)) / 2
                    if _weather:
                        _draw_weather_icon(draw, gx + icon_s / 2, ty + 12, icon_s, _weather.get('kind') or 'thermo', (0, 0, 0), 1.0)
                        gx += icon_s + 10
                    draw.text((gx, ty), txt, font=bits_font, fill=(210, 210, 210), stroke_width=1, stroke_fill=(0, 0, 0))
                canvas.save(dst_path, 'JPEG', quality=92)
                return True
            except Exception as e:
                app.logger.warning(f'make_title_frame error: {e}', exc_info=True)
                return False

        def _draw_weather_icon(draw, cx, cy, s, kind, col, a=1.0):
            """Build j: kleines Wettersymbol – gezeichnet statt Emoji, damit es auf dem Server
            auch ohne Emoji-Font erscheint. (cx, cy) Mitte, s Kantenlänge, col Kachelfarbe,
            a Deckkraft 0..1 (für das gestaffelte Einblenden)."""
            import math

            def mix(c):
                return tuple(int(round(col[i] + (c[i] - col[i]) * a)) for i in range(3))
            white, sun, blue = mix((255, 255, 255)), mix((255, 205, 80)), mix((150, 205, 255))
            lw = max(2, int(s * 0.07))

            def _sun(x, y, r, rays=8):
                for k in range(rays):
                    ang = 2 * math.pi * k / rays + math.pi / rays
                    draw.line([(x + math.cos(ang) * r * 1.35, y + math.sin(ang) * r * 1.35),
                               (x + math.cos(ang) * r * 1.85, y + math.sin(ang) * r * 1.85)], fill=sun, width=lw)
                draw.ellipse([x - r, y - r, x + r, y + r], fill=sun)

            def _cloud(x, y, w):   # Wolke der Breite w; (x, y) = Mitte der Unterkante
                h = w * 0.62
                draw.ellipse([x - w * 0.50, y - h * 0.62, x - w * 0.50 + h * 0.70, y + h * 0.08], fill=white)
                draw.ellipse([x - w * 0.26, y - h * 1.00, x - w * 0.26 + h * 0.98, y - h * 0.02], fill=white)
                draw.ellipse([x + w * 0.50 - h * 0.62, y - h * 0.55, x + w * 0.50, y + h * 0.07], fill=white)
                draw.rounded_rectangle([x - w * 0.50 + h * 0.12, y - h * 0.40, x + w * 0.50 - h * 0.08, y],
                                       radius=int(h * 0.18), fill=white)

            if kind == 'sun':
                _sun(cx, cy, s * 0.26)
            elif kind == 'partly':
                _sun(cx + s * 0.17, cy - s * 0.17, s * 0.17)
                _cloud(cx - s * 0.06, cy + s * 0.34, s * 0.78)
            elif kind in ('cloud', 'fog', 'rain', 'snow', 'storm'):
                base = cy + (s * 0.22 if kind == 'cloud' else s * 0.02)
                _cloud(cx, base, s * 0.9)
                if kind == 'fog':
                    for k in range(2):
                        yy = base + s * 0.13 + k * s * 0.15
                        draw.line([(cx - s * 0.34, yy), (cx + s * 0.34, yy)], fill=white, width=lw)
                elif kind == 'rain':
                    for k in range(3):
                        x = cx - s * 0.24 + k * s * 0.24
                        draw.line([(x + s * 0.03, base + s * 0.1), (x - s * 0.06, base + s * 0.38)], fill=blue, width=lw)
                elif kind == 'snow':
                    r = max(2, int(s * 0.055))
                    for k in range(3):
                        x = cx - s * 0.24 + k * s * 0.24
                        yy = base + s * 0.24 + (s * 0.08 if k == 1 else 0)
                        draw.ellipse([x - r, yy - r, x + r, yy + r], fill=white)
                elif kind == 'storm':
                    draw.polygon([(cx + s * 0.08, base + s * 0.02), (cx - s * 0.12, base + s * 0.24),
                                  (cx + s * 0.00, base + s * 0.24), (cx - s * 0.08, base + s * 0.46),
                                  (cx + s * 0.16, base + s * 0.18), (cx + s * 0.03, base + s * 0.18)], fill=sun)
            else:   # 'thermo' / unbekannter Code: schlichtes Thermometer
                draw.rounded_rectangle([cx - s * 0.08, cy - s * 0.34, cx + s * 0.08, cy + s * 0.12],
                                       radius=int(s * 0.08), fill=white)
                draw.ellipse([cx - s * 0.17, cy + s * 0.02, cx + s * 0.17, cy + s * 0.36], fill=mix((255, 110, 90)))

        def _fmt_hm(seconds):
            """Sekunden → 'h:mm h' (z. B. 2:45 h)."""
            m = int(round(seconds / 60))
            return f'{m // 60}:{m % 60:02d} h'

        def _draw_stats_canvas(progress, attending_count, weather, avatar_layer):
            """Statistik-Folie für einen Animationsfortschritt 0..1 – gleiche Choreografie
            wie drawStatsFrame() in touren/video.html: Kacheln blenden gestaffelt ein,
            die Zahlen zählen in den ersten 60 % hoch (ease-out), die Teilnehmer (runde
            Profilbilder + Namen, Build i) erscheinen ab 55 %. progress=1.0 = fertige Folie.
            Build j: Kacheln Fahrzeit + Ø Tempo aus den GPX-Zeitstempeln (_ride), Wetter mit
            gezeichnetem Symbol statt Emoji, im Querformat ab 5 Kacheln drei Spalten."""
            _ID = _ID_MOD
            BG, TILE = (30, 45, 80), (58, 74, 108)

            def lerp(c1, c2, a):   # Farbe c1→c2 mit Anteil a (ersetzt globalAlpha auf einfarbigem Grund)
                return tuple(int(round(c1[i] + (c2[i] - c1[i]) * a)) for i in range(3))

            canvas = _PIL.new('RGB', (W, H), BG)
            draw = _ID.Draw(canvas)
            cx = W//2
            _centered_text(draw, cx, int(H*0.10), 'Die Tour in Zahlen',
                          _pil_font(min(42, int(W/22))), (255,255,255))

            count_p = min(1.0, progress / 0.6)
            eased = 1 - (1 - count_p) ** 3           # easeOutCubic
            stats = []   # (Wert, Beschriftung, Zusatz zur Beschriftung – nur wenn er passt, Wettersymbol)
            if tour.gpx_km:     stats.append((f'{tour.gpx_km * eased:.1f} km', 'Strecke', '', None))
            if tour.gpx_ascent: stats.append((f'{int(round(tour.gpx_ascent * eased))} m', 'Höhenmeter', '', None))
            stats.append((str(int(round(attending_count * eased))), 'Dabei gewesen', '', None))
            if weather:         stats.append((f"{int(round(weather['temp_max'] * eased))}°C", 'Wetter', '',
                                              weather.get('kind') or 'thermo'))
            if _ride.get('moving_s'):   # Build j: nur wenn der GPX-Track Zeitstempel hat
                extra = ''
                if _ride.get('total_s') and _ride['total_s'] - _ride['moving_s'] >= 300:
                    extra = f" · {_fmt_hm(_ride['total_s'])} gesamt"
                stats.append((_fmt_hm(_ride['moving_s'] * eased), 'Fahrzeit', extra, None))
                if _ride.get('avg_kmh'):
                    extra = f" · max. {_ride['max_kmh']:.0f} km/h" if _ride.get('max_kmh') else ''
                    stats.append((f"{_ride['avg_kmh'] * eased:.1f} km/h", 'Ø Tempo', extra, None))

            # Raster: 2 Spalten; im Querformat ab 5 Kacheln 3 Spalten, damit die Teilnehmer noch Platz haben
            cols = 3 if (W >= H and len(stats) > 4) else 2
            gap = int(W*0.04)
            tile_w = min(int(W*0.4), int((W*0.86 - (cols-1)*gap) / cols))
            tile_h = int(H*0.15)
            start_x = cx - (cols*tile_w + (cols-1)*gap)//2
            start_y = int(H*0.28)
            big_font = _pil_font(min(52, int(W/18)))
            small_font = _pil_font(22, bold=False)
            for idx, (val, label, extra, wkind) in enumerate(stats):
                col, row = idx % cols, idx // cols
                x = start_x + col*(tile_w+gap)
                y = start_y + row*(tile_h+gap)
                a = max(0.0, min(1.0, (progress - idx*0.08) * 5))   # gestaffeltes Einblenden
                if a <= 0:
                    continue
                tile_col = lerp(BG, TILE, a)
                draw.rounded_rectangle([x, y, x+tile_w, y+tile_h], radius=16, fill=tile_col)
                tcx, ty = x + tile_w//2, y + tile_h//2 - 38
                vfont = big_font   # Wert muss in die Kachel passen (schmale 3-Spalten-Kacheln im Quadrat)
                room = tile_w - 28 - ((int(big_font.size * 1.05) + 16) if wkind else 0)
                while draw.textlength(val, font=vfont) > room and vfont.size > 30:
                    vfont = _pil_font(vfont.size - 2)
                if wkind:   # Wettersymbol links neben dem Wert, Gruppe gemeinsam zentriert
                    icon_s = int(vfont.size * 1.05)
                    tw = draw.textlength(val, font=vfont)
                    group_w = icon_s + 16 + tw
                    _draw_weather_icon(draw, tcx - group_w/2 + icon_s/2, ty + vfont.size*0.42,
                                       icon_s, wkind, tile_col, a)
                    tcx = int(tcx + group_w/2 - tw/2)
                _centered_text(draw, tcx, ty, val, vfont, lerp(tile_col, (255,255,255), a))
                if extra and draw.textlength(label + extra, font=small_font) <= tile_w - 24:
                    label += extra
                _centered_text(draw, x+tile_w//2, y+tile_h//2+16, label, small_font, lerp(tile_col, (210,210,210), a))

            if avatar_layer is not None and progress > 0.55:
                a = min(1.0, (progress - 0.55) * 3)
                row = avatar_layer.copy()
                if a < 1:
                    row.putalpha(row.getchannel('A').point(lambda v: int(v * a)))
                rows_bottom = start_y + ((len(stats) + cols - 1) // cols) * (tile_h + gap)
                row_top = max(rows_bottom + 30, H - SAFE - 70 - row.height)
                canvas.paste(row, (0, row_top), row)
            paste_watermark(canvas, 'tr')
            return canvas

        def build_stats_frames(attending_count, weather, users_info):
            """Animierte Statistik-Folie (4 s) als Einzelbilder für frames_to_segment():
            15 Bilder/s bis alles steht (3,6 s), danach ein Haltebild."""
            if not PIL_OK:
                return []
            try:
                avatar_layer = _avatar_row_layer(users_info)   # einmal bauen, pro Bild nur einblenden
                total, anim_secs, step_fps = 4.0, 3.6, 15
                n_anim = int(anim_secs * step_fps)
                frames = []
                for i in range(n_anim):
                    progress = (i / step_fps) / total
                    fpath = os.path.join(tmpdir, f'stats_{i:03d}.jpg')
                    _draw_stats_canvas(progress, attending_count, weather, avatar_layer).save(fpath, 'JPEG', quality=88)
                    frames.append((fpath, round(1 / step_fps, 4)))
                fpath = os.path.join(tmpdir, 'stats_hold.jpg')
                _draw_stats_canvas(1.0, attending_count, weather, avatar_layer).save(fpath, 'JPEG', quality=88)
                frames.append((fpath, round(total - anim_secs, 3)))
                return frames
            except Exception as e:
                app.logger.warning(f'build_stats_frames error: {e}', exc_info=True)
                return []

        def make_stats_frame(dst_path, attending_count, weather, users_info=None):
            """Statische Statistik-Folie (Fallback, falls die Animation nicht gebaut werden kann)."""
            if not PIL_OK:
                return False
            try:
                _draw_stats_canvas(1.0, attending_count, weather,
                                   _avatar_row_layer(users_info or [])).save(dst_path, 'JPEG', quality=92)
                return True
            except Exception as e:
                app.logger.warning(f'make_stats_frame error: {e}', exc_info=True)
                return False

        def build_gastro_frames(spots):
            """Build j: Folie „Einkehr unterwegs“ – Gastro-Einträge höchstens GASTRO_NEAR_M m
            neben dem Track (gastro_near_track), mit Art, Streckenkilometer und Abstand;
            Zeilen blenden gestaffelt ein. Liefert [(frame, dauer), …] für
            frames_to_segment() oder [] (keine Treffer / Fehler)."""
            if not PIL_OK or not spots:
                return []
            try:
                _ID = _ID_MOD
                BG, TILE, MARK = (30, 45, 80), (58, 74, 108), (142, 36, 170)

                def lerp(c1, c2, a):
                    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * a)) for i in range(3))

                rows = spots[:6]
                more = len(spots) - len(rows)
                title_font = _pil_font(min(42, int(W/22)))
                name_font  = _pil_font(min(40, int(W/27)))
                sub_font   = _pil_font(22, bold=False)
                row_w, row_h, gap = int(W*0.86), max(96, int(H*0.085)), 18
                x0, y0 = (W - row_w)//2, int(H*0.22)

                def draw_slide(progress):
                    canvas = _PIL.new('RGB', (W, H), BG)
                    draw = _ID.Draw(canvas)
                    _centered_text(draw, W//2, int(H*0.10), 'Einkehr unterwegs', title_font, (255, 255, 255))
                    _centered_text(draw, W//2, int(H*0.10) + title_font.size + 14,
                                   f'Gastronomie direkt an der Strecke (bis {GASTRO_NEAR_M} m)', sub_font, (190, 200, 220))
                    for i, sp in enumerate(rows):
                        a = max(0.0, min(1.0, (progress - 0.1 - i*0.1) * 4))
                        if a <= 0:
                            continue
                        y = y0 + i*(row_h + gap)
                        tile_col = lerp(BG, TILE, a)
                        draw.rounded_rectangle([x0, y, x0 + row_w, y + row_h], radius=16, fill=tile_col)
                        mx, my = x0 + 40, y + row_h//2
                        draw.ellipse([mx-12, my-12, mx+12, my+12], fill=lerp(tile_col, MARK, a),
                                     outline=lerp(tile_col, (255, 255, 255), a), width=3)
                        name = sp['name']
                        if draw.textlength(name, font=name_font) > row_w - 110:
                            while len(name) > 4 and draw.textlength(name + '…', font=name_font) > row_w - 110:
                                name = name[:-1].rstrip()
                            name += '…'
                        draw.text((x0 + 76, y + row_h//2 - name_font.size - 2), name, font=name_font,
                                  fill=lerp(tile_col, (255, 255, 255), a))
                        if sp.get('planned') and not sp.get('km_known'):     # Build x
                            sub = f"Geplante Einkehr · {sp['type_label']}"
                        else:
                            sub = (f"{sp['type_label']} · km {sp['km']:.1f}".replace('.', ',') +
                                   f" · {sp['dist_m']} m neben der Route" +
                                   (' · geplant' if sp.get('planned') else ''))
                        draw.text((x0 + 76, y + row_h//2 + 6), sub, font=sub_font, fill=lerp(tile_col, (210, 210, 210), a))
                    if more > 0:
                        a = max(0.0, min(1.0, (progress - 0.1 - len(rows)*0.1) * 4))
                        if a > 0:
                            _centered_text(draw, W//2, y0 + len(rows)*(row_h + gap) + 8, f'… und {more} weitere',
                                           sub_font, lerp(BG, (210, 210, 210), a))
                    paste_watermark(canvas, 'tr')
                    return canvas

                total = min(6.0, 2.5 + 0.5*len(rows))
                anim_secs, step_fps = min(total - 0.4, 1.2 + 0.4*len(rows)), 15
                frames = []
                for i in range(int(anim_secs * step_fps)):
                    progress = (i / step_fps) / anim_secs
                    fpath = os.path.join(tmpdir, f'gastro_{i:03d}.jpg')
                    draw_slide(progress).save(fpath, 'JPEG', quality=88)
                    frames.append((fpath, round(1 / step_fps, 4)))
                fpath = os.path.join(tmpdir, 'gastro_hold.jpg')
                draw_slide(1.0).save(fpath, 'JPEG', quality=88)
                frames.append((fpath, round(total - anim_secs, 3)))
                return frames
            except Exception as e:
                app.logger.warning(f'build_gastro_frames error: {e}', exc_info=True)
                return []

        def build_profile_frames(gpx_points):
            """Build n: animiertes Höhenprofil (3,5 s) wie in der Browser-Vorschau – die Kurve
            baut sich von links nach rechts auf (gefüllte Fläche + Linie), mit Höhen-Raster,
            km-Achse, laufendem Höhenwert an der Spitze und Markierung des höchsten Punkts.
            x-Achse = echte Streckenkilometer. Ohne Höhendaten (flacher als 1 m) → [].
            Liefert [(frame, dauer), …] für frames_to_segment()."""
            if not PIL_OK or not gpx_points or len(gpx_points) < 2:
                return []
            try:
                import math
                _ID = _ID_MOD
                from PIL import ImageChops as _ICH
                step = max(1, len(gpx_points) // 300)
                pts = gpx_points[::step]
                if step > 1 and (len(gpx_points) - 1) % step:
                    pts.append(gpx_points[-1])
                raw = [float(p.get('ele') or 0) for p in pts]
                k = 2                                                   # Glättung: Mittel über 5 Punkte
                eles = [sum(raw[max(0, i - k):i + k + 1]) / len(raw[max(0, i - k):i + k + 1]) for i in range(len(raw))]
                e_min, e_max = min(eles), max(eles)
                if e_max - e_min < 1 or not any(raw):
                    return []
                m_lat = 111320.0
                m_lng = 111320.0 * max(0.2, math.cos(math.radians(pts[0]['lat'])))
                dist = [0.0]
                for a, b in zip(pts, pts[1:]):
                    dist.append(dist[-1] + math.hypot((b['lat'] - a['lat']) * m_lat, (b['lng'] - a['lng']) * m_lng))
                total_m = dist[-1] or 1.0
                i_max = eles.index(e_max)

                BG, LINE, GRID, TXT = (30, 45, 80), (100, 181, 246), (70, 90, 130), (190, 200, 220)
                left, right = SAFE + 95, W - SAFE - 40
                top = int(H * 0.28)
                bottom = int(H * 0.62) if H > W * 1.2 else int(H * 0.80)
                lo = e_min - (e_max - e_min) * 0.05
                hi = e_max + (e_max - e_min) * 0.10

                def X(i):
                    return left + (right - left) * dist[i] / total_m

                def Y(e):
                    return bottom - (bottom - top) * (e - lo) / (hi - lo)

                # Raster-Schritte so wählen, dass 3–6 Linien bzw. höchstens 8 km-Marken entstehen
                e_step = next((st for st in (5, 10, 20, 25, 50, 100, 200, 500, 1000) if (hi - lo) / st <= 6), 1000)
                km_step = next((st for st in (1, 2, 5, 10, 20, 25, 50, 100) if total_m / 1000 / st <= 8), 100)
                title_font = _pil_font(min(42, int(W / 22)))
                sub_font = _pil_font(24, bold=False)
                ax_font = _pil_font(20, bold=False)
                tip_font = _pil_font(24)
                curve = [(X(i), Y(eles[i])) for i in range(len(pts))]
                # Vertikaler Verlauf für die Füllung (oben kräftig, unten schwach), einmal vorbereitet
                grad = _PIL.linear_gradient('L').rotate(180).resize((W, max(1, bottom - top)))
                grad = grad.point(lambda v: int(18 + v * 0.45))
                alpha_full = _PIL.new('L', (W, H), 0)
                alpha_full.paste(grad, (0, top))
                date_str = tour.tour_date.strftime('%d.%m.%Y') if (tour.tour_date and not tour.is_date_open) else ''
                sub_bits = [b for b in (date_str, f'{tour.gpx_km} km' if tour.gpx_km else '',
                                        f'{int(tour.gpx_ascent)} Hm' if tour.gpx_ascent else '') if b]

                def draw_slide(progress):
                    canvas = _PIL.new('RGB', (W, H), BG)
                    draw = _ID.Draw(canvas)
                    _centered_text(draw, W // 2, int(H * 0.10), 'Höhenprofil', title_font, (255, 255, 255))
                    if sub_bits:
                        _centered_text(draw, W // 2, int(H * 0.10) + title_font.size + 14, '  ·  '.join(sub_bits), sub_font, TXT)
                    # Höhen-Raster (gepunktet) + Beschriftung
                    e_t = math.ceil(lo / e_step) * e_step
                    while e_t <= hi:
                        y = Y(e_t)
                        for x in range(left, right, 14):
                            draw.line([(x, y), (min(x + 6, right), y)], fill=GRID, width=2)
                        lbl = f'{int(e_t)} m'
                        draw.text((left - 12 - draw.textlength(lbl, font=ax_font), y - ax_font.size * 0.65), lbl, font=ax_font, fill=TXT)
                        e_t += e_step
                    # km-Achse
                    draw.line([(left, bottom), (right, bottom)], fill=GRID, width=2)
                    km_t = 0
                    while km_t * 1000 <= total_m + 1:
                        x = left + (right - left) * (km_t * 1000) / total_m
                        draw.line([(x, bottom), (x, bottom + 8)], fill=GRID, width=2)
                        lbl = f'{km_t} km' if km_t else '0'
                        draw.text((x - draw.textlength(lbl, font=ax_font) / 2, bottom + 12), lbl, font=ax_font, fill=TXT)
                        km_t += km_step
                    # Kurve bis zum Fortschritt: Fläche mit Verlauf + Linie
                    end = max(2, int(round(len(pts) * min(1.0, progress))))
                    seg = curve[:end]
                    poly = _PIL.new('L', (W, H), 0)
                    _ID.Draw(poly).polygon([(seg[0][0], bottom)] + seg + [(seg[-1][0], bottom)], fill=255)
                    canvas.paste(LINE, (0, 0), _ICH.multiply(poly, alpha_full))
                    draw.line(seg, fill=LINE, width=5, joint='curve')
                    # höchster Punkt, sobald erreicht
                    if i_max < end - 1 or progress >= 1:
                        mx, my = curve[i_max]
                        draw.ellipse([mx - 6, my - 6, mx + 6, my + 6], fill=(255, 255, 255))
                        if progress >= 1 or abs(seg[-1][0] - mx) > 90:
                            lbl = f'↑ {int(round(e_max))} m'
                            tw = draw.textlength(lbl, font=ax_font)
                            draw.text((min(max(left, mx - tw / 2), right - tw), my - 34), lbl, font=ax_font, fill=(255, 255, 255))
                    # Spitze mit laufendem Höhenwert
                    if progress < 1:
                        tx, ty = seg[-1]
                        draw.ellipse([tx - 9, ty - 9, tx + 9, ty + 9], fill=LINE, outline=(255, 255, 255), width=3)
                        lbl = f'{int(round(eles[end - 1]))} m'
                        tw = draw.textlength(lbl, font=tip_font)
                        lx = tx + 16 if tx + 16 + tw < right else tx - 16 - tw
                        draw.text((lx, ty - tip_font.size - 6), lbl, font=tip_font, fill=(255, 255, 255),
                                  stroke_width=2, stroke_fill=BG)
                    paste_watermark(canvas, 'tr')
                    return canvas

                total, anim_secs, step_fps = 3.5, 2.6, 15
                frames = []
                for i in range(int(anim_secs * step_fps)):
                    fpath = os.path.join(tmpdir, f'profile_{i:03d}.jpg')
                    draw_slide((i / step_fps) / anim_secs).save(fpath, 'JPEG', quality=88)
                    frames.append((fpath, round(1 / step_fps, 4)))
                fpath = os.path.join(tmpdir, 'profile_hold.jpg')
                draw_slide(1.0).save(fpath, 'JPEG', quality=88)
                frames.append((fpath, round(total - anim_secs, 3)))
                return frames
            except Exception as e:
                app.logger.warning(f'build_profile_frames error: {e}', exc_info=True)
                return []

        def make_outro_frame(dst_path, group_name):
            if not PIL_OK:
                return False
            try:
                _ID = _ID_MOD
                canvas = _cover_photo_bg((W, H))
                draw = _ID.Draw(canvas)
                cx, cy = W//2, H//2
                lg = _logo_scaled(int(H * 0.12))          # Build i: Gruppenlogo über dem Dank
                if lg is not None:
                    canvas.paste(lg, (cx - lg.width // 2, cy - 60 - lg.height - 36), lg)
                _centered_text(draw, cx, cy-60, 'Danke fürs Mitfahren!',
                              _pil_font(min(46, int(W/16))), (255,255,255),
                              stroke_width=2, stroke_fill=(0,0,0))
                _centered_text(draw, cx, cy+10, group_name, _pil_font(28, bold=False), (220,220,220))
                # Mitmach-Aufforderung – Gruppenname explizit mit nennen, da eine
                # Domain mehrere unterschiedliche Gruppen bedienen kann
                base_url = app.config.get('BASE_URL', '') or ''
                domain = base_url.replace('https://', '').replace('http://', '').rstrip('/')
                if domain and domain != 'localhost:5000':
                    name_short = group_name if len(group_name) <= 22 else group_name[:19] + '…'
                    _centered_text(draw, cx, cy+70, f'Noch nicht bei „{name_short}" dabei?',
                                  _pil_font(20, bold=False), (190,190,190))
                    _centered_text(draw, cx, cy+105, domain,
                                  _pil_font(30), (255, 196, 0))
                canvas.save(dst_path, 'JPEG', quality=92)
                return True
            except Exception as e:
                app.logger.warning(f'make_outro_frame error: {e}', exc_info=True)
                return False

        def _lat_lng_to_tile_xy(lat, lng, zoom):
            import math
            n = 2 ** zoom
            x = (lng + 180.0) / 360.0 * n
            y = (1.0 - math.log(math.tan(lat*math.pi/180.0) + 1.0/math.cos(lat*math.pi/180.0)) / math.pi) / 2.0 * n
            return x, y

        def build_track_frames(gpx_points, photos_with_gps, near_spots=None):
            """Lädt echte OSM-Kacheln + zeichnet den Track schrittweise animiert.
            Gibt Liste von (frame_path, duration) zurück, oder [] bei Fehler/keinen Daten.
            Build j: near_spots (gastro_near_track) erscheinen als Marker mit Namensschild,
            sobald der gezeichnete Track an ihnen vorbeikommt.
            Build k: Der Track füllt die Kartenfläche (größte passende Zoomstufe, bei unter
            66 % Füllung eine Stufe feiner + Kachelbild auf 70–100 % skaliert). Foto-Marker
            sind kleiner, werden gebündelt („+N“) und NEBEN dem Track platziert – an der von
            8 Positionen, die am wenigsten Track verdeckt – mit Verbindungslinie zum
            Aufnahmeort. GPS-Fotos weit abseits des Tracks (falsche EXIF-Position) werden
            ignoriert, damit sie den Kartenausschnitt nicht aufblähen."""
            if not PIL_OK or not gpx_points or len(gpx_points) < 2:
                return []
            try:
                import math
                _ID = _ID_MOD
                step = max(1, len(gpx_points)//300)
                pts = gpx_points[::step]
                t_lats = [p['lat'] for p in pts]; t_lngs = [p['lng'] for p in pts]
                pad_lat = max(0.02, (max(t_lats) - min(t_lats)) * 0.25)
                pad_lng = max(0.03, (max(t_lngs) - min(t_lngs)) * 0.25)
                photos_with_gps = [p for p in photos_with_gps
                                   if min(t_lats) - pad_lat <= p['lat'] <= max(t_lats) + pad_lat
                                   and min(t_lngs) - pad_lng <= p['lng'] <= max(t_lngs) + pad_lng]
                lats = t_lats + [p['lat'] for p in photos_with_gps]
                lngs = t_lngs + [p['lng'] for p in photos_with_gps]
                min_lat, max_lat = min(lats), max(lats)
                min_lng, max_lng = min(lngs), max(lngs)

                # Kartenfläche: unter der Kopfzeile (24..88) bis über die ©-Zeile, Rand für Marker
                TILE = 256
                map_top, map_bottom = 100, H - 40
                avail_w, avail_h = W - 140, (map_bottom - map_top) - 80
                center_y = (map_top + map_bottom) / 2

                def extent(z):
                    x1, y1 = _lat_lng_to_tile_xy(min_lat, min_lng, z)
                    x2, y2 = _lat_lng_to_tile_xy(max_lat, max_lng, z)
                    return abs(x2 - x1) * TILE, abs(y1 - y2) * TILE

                zoom = 16
                while zoom > 8:
                    ew, eh = extent(zoom)
                    if ew <= avail_w and eh <= avail_h:
                        break
                    zoom -= 1
                ew, eh = extent(zoom)
                fill = max(ew / avail_w, eh / avail_h, 1e-6)
                f = 1.0                                   # Feinskalierung des Kachelbilds
                if fill > 1:                              # selbst Zoom 8 zu groß (Extremfall)
                    f = max(0.5, 0.92 / fill)
                elif fill < 0.66 and zoom < 17:
                    zoom += 1
                    f = min(1.0, 0.92 / (2 * fill))

                center_lat, center_lng = (min_lat + max_lat) / 2, (min_lng + max_lng) / 2
                c_x, c_y = _lat_lng_to_tile_xy(center_lat, center_lng, zoom)
                src_w, src_h = W / f, H / f                               # Quellbereich in Kachelpixeln
                src_left, src_top = c_x * TILE - (W / 2) / f, c_y * TILE - center_y / f
                start_tx, end_tx = int(math.floor(src_left / TILE)), int(math.floor((src_left + src_w) / TILE))
                start_ty, end_ty = int(math.floor(src_top / TILE)), int(math.floor((src_top + src_h) / TILE))
                tiles_across, tiles_down = end_tx - start_tx + 1, end_ty - start_ty + 1

                bg = _PIL.new('RGB', (tiles_across * TILE, tiles_down * TILE), (230, 235, 225))
                subdomains = ['a', 'b', 'c']
                for tx in range(tiles_across):
                    for ty in range(tiles_down):
                        sub = subdomains[(tx * tiles_down + ty) % 3]
                        url = f'https://{sub}.tile.openstreetmap.org/{zoom}/{start_tx + tx}/{start_ty + ty}.png'
                        try:
                            r = http_requests.get(url, timeout=4,
                                                  headers={'User-Agent': 'DjO-RadgruppenApp/1.0'})
                            if r.status_code == 200:
                                tile_img = _PIL.open(io.BytesIO(r.content)).convert('RGB')
                                bg.paste(tile_img, (tx * TILE, ty * TILE))
                        except Exception:
                            pass
                sx, sy = src_left - start_tx * TILE, src_top - start_ty * TILE
                base = bg.crop((int(round(sx)), int(round(sy)), int(round(sx + src_w)), int(round(sy + src_h))))
                if base.size != (W, H):
                    base = base.resize((W, H), _PIL.LANCZOS)

                def proj(lat, lng):
                    px, py = _lat_lng_to_tile_xy(lat, lng, zoom)
                    return ((px - c_x) * TILE * f + W / 2, (py - c_y) * TILE * f + center_y)

                # Foto-Marker: Position, Streckenanteil, Bündelung nahe beieinanderliegender Fotos
                thumb = max(44, min(90, int(round(min(W, H) * 0.084))))   # 90 px bei 1080er Formaten (Build l)
                items = []
                for i, p in enumerate(photos_with_gps):
                    best_d, best_i = 1e18, 0
                    for k, pt in enumerate(pts):
                        d = (pt['lat'] - p['lat']) ** 2 + (pt['lng'] - p['lng']) ** 2
                        if d < best_d:
                            best_d, best_i = d, k
                    x, y = proj(p['lat'], p['lng'])
                    items.append({'idx': i, 'x': x, 'y': y, 'frac': best_i / len(pts)})
                clusters = []
                for it in items:
                    for c in clusters:
                        if math.hypot(c['x'] - it['x'], c['y'] - it['y']) < thumb * 0.9:
                            c['count'] += 1
                            c['frac'] = min(c['frac'], it['frac'])
                            break
                    else:
                        clusters.append(dict(it, count=1))
                # Platzierung: von 8 Positionen um den Aufnahmeort die mit der geringsten Überdeckung
                # (Trackpunkte in der Kachel ×10, Kollision mit anderer Kachel ×1000, außerhalb ×10000)
                track_xy = [proj(pt['lat'], pt['lng']) for pt in pts]
                dd = thumb / 2 + 24
                cands = [(0, -dd), (dd, 0), (-dd, 0), (0, dd),
                         (0.8 * dd, -0.8 * dd), (-0.8 * dd, -0.8 * dd), (0.8 * dd, 0.8 * dd), (-0.8 * dd, 0.8 * dd)]
                placed = []
                for c in clusters:
                    best = None
                    for ci, (dx, dy) in enumerate(cands):
                        tx_, ty_ = c['x'] + dx, c['y'] + dy
                        l, t, r, b = tx_ - thumb / 2 - 8, ty_ - thumb / 2 - 8, tx_ + thumb / 2 + 8, ty_ + thumb / 2 + 8
                        cost = ci * 0.5                           # leichte Vorliebe: oben, rechts, links, unten
                        if l < 6 or r > W - 6 or t < map_top or b > H - 36:
                            cost += 10000
                        cost += 10 * sum(1 for (px_, py_) in track_xy if l <= px_ <= r and t <= py_ <= b)
                        cost += 1000 * sum(1 for pr in placed if not (r < pr[0] or l > pr[2] or b < pr[1] or t > pr[3]))
                        if best is None or cost < best[0]:
                            best = (cost, tx_, ty_, (l, t, r, b))
                    c['tx'], c['ty'] = best[1], best[2]
                    placed.append(best[3])
                    src = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photos_with_gps[c['idx']]['filename'])
                    c['img'] = None
                    if os.path.exists(src):
                        try:
                            pimg = _PIL.open(src).convert('RGB')
                            sq = min(pimg.width, pimg.height)
                            pimg = pimg.crop(((pimg.width - sq) // 2, (pimg.height - sq) // 2,
                                              (pimg.width - sq) // 2 + sq, (pimg.height - sq) // 2 + sq))
                            c['img'] = pimg.resize((thumb, thumb), _PIL.LANCZOS)
                        except Exception:
                            pass
                badge_font = _pil_font(13)

                N_STEPS = 16
                frame_paths = []
                for step_i in range(1, N_STEPS + 1):
                    progress = step_i / N_STEPS
                    frame = base.copy()
                    draw = _ID.Draw(frame)

                    end_idx = max(1, int(len(pts) * progress))
                    line_pts = [proj(pt['lat'], pt['lng']) for pt in pts[:end_idx]]
                    if len(line_pts) > 1:
                        draw.line(line_pts, fill=(255, 255, 255), width=13, joint='curve')
                        draw.line(line_pts, fill=(240, 133, 30), width=8, joint='curve')

                    sx_, sy_ = proj(pts[0]['lat'], pts[0]['lng'])
                    draw.ellipse([sx_ - 13, sy_ - 13, sx_ + 13, sy_ + 13], fill=(46, 125, 50), outline=(255, 255, 255), width=4)
                    if progress >= 0.99:
                        ex, ey = proj(pts[-1]['lat'], pts[-1]['lng'])
                        draw.ellipse([ex - 13, ey - 13, ex + 13, ey + 13], fill=(198, 40, 40), outline=(255, 255, 255), width=4)

                    reached = end_idx / len(pts)
                    for c in clusters:
                        if c['frac'] > reached or c['img'] is None:
                            continue
                        x, y, tx_, ty_ = c['x'], c['y'], c['tx'], c['ty']
                        draw.line([(x, y), (tx_, ty_)], fill=(255, 255, 255), width=5)
                        draw.line([(x, y), (tx_, ty_)], fill=(43, 63, 107), width=2)
                        draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(43, 63, 107), outline=(255, 255, 255), width=2)
                        fx, fy = int(tx_ - thumb / 2), int(ty_ - thumb / 2)
                        draw.rounded_rectangle([fx - 3, fy - 3, fx + thumb + 3, fy + thumb + 3], radius=7, fill=(255, 255, 255))
                        frame.paste(c['img'], (fx, fy))
                        if c['count'] > 1:                     # „+N“-Plakette oben rechts
                            bx, by = fx + thumb - 2, fy + 2
                            draw.ellipse([bx - 12, by - 12, bx + 12, by + 12], fill=(240, 133, 30), outline=(255, 255, 255), width=2)
                            _centered_text(draw, bx, by - 8, f"+{c['count'] - 1}", badge_font, (255, 255, 255))

                    # Build j: Einkehr an der Route – Marker (+ Namensschild bei bis zu 6 Treffern)
                    spot_font = _pil_font(18)
                    for sp in (near_spots or [])[:12]:
                        if sp['frac'] > reached:
                            continue
                        x, y = proj(sp['lat'], sp['lng'])
                        draw.ellipse([x-11, y-11, x+11, y+11], fill=(142, 36, 170), outline=(255, 255, 255), width=3)
                        if len(near_spots) <= 6:
                            lbl = sp['name'][:26]
                            tw = draw.textlength(lbl, font=spot_font)
                            bx = x + 16 if x + 16 + tw + 16 < W - 8 else x - 16 - tw - 16
                            by = y - 15
                            draw.rounded_rectangle([bx, by, bx + tw + 16, by + 30], radius=8,
                                                   fill=(255, 255, 255), outline=(142, 36, 170), width=2)
                            draw.text((bx + 8, by + 5), lbl, font=spot_font, fill=(40, 40, 40))

                    draw.rounded_rectangle([24,24,W-24,88], radius=10, fill=(20,30,20))
                    draw.text((42,38), tour.title[:34], font=_pil_font(min(26,int(W/24))), fill=(255,255,255))
                    pct_text = f'{int(progress*100)}% der Strecke'
                    if tour.gpx_km:   # Build m: gefahrene / gesamte km wie in der Vorschau
                        pct_text += f' · {tour.gpx_km * progress:.1f} / {tour.gpx_km} km'
                    draw.text((42,64), pct_text, font=_pil_font(18, bold=False), fill=(220,220,220))
                    draw.text((W-190, H-34), '\u00A9 OpenStreetMap', font=_pil_font(16, bold=False), fill=(0,0,0))
                    paste_watermark(frame, 'bl')

                    fpath = os.path.join(tmpdir, f'track_{step_i:03d}.jpg')
                    frame.convert('RGB').save(fpath, 'JPEG', quality=88)
                    frame_paths.append(fpath)

                per_frame_dur = round(max(2.5, min(9, 3 + len(photos_with_gps))) / N_STEPS, 3)
                return [(p, per_frame_dur) for p in frame_paths]
            except Exception as e:
                app.logger.warning(f'build_track_frames error: {e}', exc_info=True)
                return []

        # ── Fotos verarbeiten ─────────────────────────────────────────────────
        concat_file = os.path.join(tmpdir, 'concat.txt')
        n_valid = 0

        # Zusatzdaten für Stats-Folie (gleiche Werte wie in der Vorschau)
        _attending_count = TourParticipant.query.filter_by(
            tour_id=tour_id, status='attending'
        ).count()
        _attending_users = [(p.user.display_name, p.user.avatar) for p in
                            TourParticipant.query.filter_by(tour_id=tour_id, status='attending')
                            .join(User).order_by(User.name).limit(12).all()]
        _weather = _tour_day_weather(tour)   # Build j: gemeinsamer Helfer (Prognose + Archiv)

        from flask import g as _g_render
        _grp = getattr(_g_render, 'group', None)
        _group_name = _grp.name if _grp else 'De jungen Olen'
        # Build i: Gruppenlogo einmal laden (Wasserzeichen, Titel, Outro)
        logo_rgba = None
        if PIL_OK and _grp and _grp.logo:
            _logo_path = os.path.join(app.root_path, 'static', 'uploads', 'group_logos', _grp.logo)
            if os.path.exists(_logo_path):
                try:
                    logo_rgba = _logo_auto_alpha(_PIL.open(_logo_path))   # Build m: Hintergrund freistellen
                except Exception:
                    logo_rgba = None

        show_track  = request.form.get('show_track', '1') == '1'
        show_stats  = request.form.get('show_stats', '1') == '1'
        show_gastro = request.form.get('show_gastro', '1') == '1'   # Build j: Einkehr-Folie + Karten-Marker
        show_profile = request.form.get('show_profile', '1') == '1' # Build n: Höhenprofil-Folie (wie Vorschau)
        _slide_secs = 0.0  # Summe aller Folien-Sekunden (für Audio-Fade-Timing)

        # GPX einmal parsen: Punkte für die Karte, Zeitstempel für Fahrzeit/Schnitt (Build j),
        # Einkehr nahe der Route (Build j)
        _gpx_points, _ride, _near_spots, _mini_track = [], {}, [], None
        if tour.gpx_file:
            _gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
            if os.path.exists(_gpx_path):
                _parsed = parse_gpx(_gpx_path)
                if _parsed:
                    _gpx_points = _parsed.get('points', [])
                    _ride = {k: _parsed.get(k) for k in ('moving_s', 'total_s', 'avg_kmh', 'max_kmh')}
        if show_gastro and _gpx_points:
            _near_spots = gastro_near_track(_gpx_points)
        if show_gastro:                                   # Build x: geplante Einkehr immer zuerst
            _planned = _planned_einkehr_entry(tour, _gpx_points)
            if _planned:
                _near_spots = [_planned] + [sp for sp in _near_spots if sp.get('id') != _planned['id']]
        if len(_gpx_points) >= 2:   # Build o: Track-Umriss + km-Stände für die Mini-Karte auf den Fotos
            try:
                import math as _m
                _st = max(1, len(_gpx_points) // 300)
                _mp = _gpx_points[::_st]
                if _st > 1 and (len(_gpx_points) - 1) % _st:
                    _mp.append(_gpx_points[-1])
                _lats = [q['lat'] for q in _mp]; _lngs = [q['lng'] for q in _mp]
                _cos = max(0.2, _m.cos(_m.radians((min(_lats) + max(_lats)) / 2)))
                _cum = [0.0]
                for _a, _b in zip(_mp, _mp[1:]):
                    _cum.append(_cum[-1] + _m.hypot((_b['lat'] - _a['lat']) * 111320.0, (_b['lng'] - _a['lng']) * 111320.0 * _cos))
                _mini_track = {'pts': _mp, 'cum_km': [c_ / 1000 for c_ in _cum], 'cos': _cos,
                               'min_lat': min(_lats), 'max_lat': max(_lats), 'min_lng': min(_lngs), 'max_lng': max(_lngs)}
            except Exception:
                _mini_track = None
        _photos_with_gps = [{'filename': p.filename, 'lat': p.lat, 'lng': p.lng}
                            for p in photos if p.lat and p.lng]

        with open(concat_file, 'w') as cf:
            # 1. Titelfolie (3s) – als Video-Segment
            title_frame = os.path.join(tmpdir, 'slide_title.jpg')
            title_seg   = os.path.join(tmpdir, 'seg_title.mp4')
            if make_title_frame(title_frame) and image_to_segment(title_frame, title_seg, 3):
                cf.write(f"file '{title_seg}'\n")
                _slide_secs += 3

            # 1b. Kartenfolie: animierter Track, zu EINEM Video-Segment zusammengefasst
            if show_track and _gpx_points:
                track_frames = build_track_frames(_gpx_points, _photos_with_gps, _near_spots)
                if track_frames:
                    track_seg = os.path.join(tmpdir, 'seg_track.mp4')
                    track_dur = sum(d for _, d in track_frames)
                    if frames_to_segment(track_frames, track_seg):
                        cf.write(f"file '{track_seg}'\n")
                        _slide_secs += track_dur

            # 1c. Einkehr-Folie (Build j): Gastro-Einträge nahe der Route, nur wenn es Treffer gibt
            if show_gastro and _near_spots:
                gastro_frames = build_gastro_frames(_near_spots)
                if gastro_frames:
                    gastro_seg = os.path.join(tmpdir, 'seg_gastro.mp4')
                    if frames_to_segment(gastro_frames, gastro_seg):
                        cf.write(f"file '{gastro_seg}'\n")
                        _slide_secs += sum(d for _, d in gastro_frames)

            # 2. Statistik-Folie (4 s) – Zahlen zählen animiert hoch wie in der Browser-
            #    Vorschau (Build h), als EIN Video-Segment; Fallback: statisches Bild
            if show_stats:
                stats_seg = os.path.join(tmpdir, 'seg_stats.mp4')
                stats_frames = build_stats_frames(_attending_count, _weather, _attending_users)
                if stats_frames and frames_to_segment(stats_frames, stats_seg):
                    cf.write(f"file '{stats_seg}'\n")
                    _slide_secs += sum(d for _, d in stats_frames)
                else:
                    stats_frame = os.path.join(tmpdir, 'slide_stats.jpg')
                    if make_stats_frame(stats_frame, _attending_count, _weather, _attending_users) and \
                       image_to_segment(stats_frame, stats_seg, 4):
                        cf.write(f"file '{stats_seg}'\n")
                        _slide_secs += 4

            # 3. Fotos (mit flüssigem Ken-Burns-Zoom via FFmpeg zoompan-Filter)
            for i, p in enumerate(photos):
                src = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], p.filename)
                if not os.path.exists(src):
                    continue
                oriented = os.path.join(tmpdir, f'oriented_{i:04d}.jpg')
                auto_orient(src, oriented)
                zoom_in = (i % 2 == 0)  # abwechselnd rein-/rauszoomen für Abwechslung
                # Build i: Overlay mit Logo + Uhrzeit/Bildunterschrift (None, wenn nichts zu zeigen)
                overlay_png = os.path.join(tmpdir, f'overlay_{i:04d}.png')
                if not (PIL_OK and make_photo_overlay(p, overlay_png)):
                    overlay_png = None
                segment_path = os.path.join(tmpdir, f'photo_{i:04d}.mp4')
                if make_photo_zoom_segment(oriented, segment_path, photo_dur, zoom_in=zoom_in,
                                           overlay_png=overlay_png):
                    cf.write(f"file '{segment_path}'\n")
                    _slide_secs += photo_dur
                    n_valid += 1
                else:
                    # Fallback: Standbild ohne Zoom, als Video-Segment (nicht als Bild-Zeile!)
                    frame = os.path.join(tmpdir, f'frame_{i:04d}.jpg')
                    fallback_seg = os.path.join(tmpdir, f'photo_fallback_{i:04d}.mp4')
                    make_frame(oriented, frame, overlay_png)
                    if image_to_segment(frame, fallback_seg, photo_dur):
                        cf.write(f"file '{fallback_seg}'\n")
                        _slide_secs += photo_dur
                        n_valid += 1

            # 3b. Höhenprofil (Build n) – animiert, nach den Fotos wie in der Browser-Vorschau
            if show_profile and _gpx_points:
                prof_frames = build_profile_frames(_gpx_points)
                if prof_frames:
                    prof_seg = os.path.join(tmpdir, 'seg_profile.mp4')
                    if frames_to_segment(prof_frames, prof_seg):
                        cf.write(f"file '{prof_seg}'\n")
                        _slide_secs += sum(d for _, d in prof_frames)

            # 4. Outro (6s – lang genug um Gruppenname + Domain lesen zu können)
            outro_frame = os.path.join(tmpdir, 'slide_outro.jpg')
            outro_seg   = os.path.join(tmpdir, 'seg_outro.mp4')
            OUTRO_DUR = 6
            if make_outro_frame(outro_frame, _group_name) and image_to_segment(outro_frame, outro_seg, OUTRO_DUR):
                cf.write(f"file '{outro_seg}'\n")
                _slide_secs += OUTRO_DUR

        if n_valid == 0:
            flash('Foto-Dateien nicht gefunden.', 'danger')
            return redirect(url_for('tour_video', tour_id=tour_id))

        total_secs = _slide_secs

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
        try:
            os.remove(lock_path)                        # Build ab: Render-Sperre freigeben
        except OSError:
            pass
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
        # Audit 1.4.0: ungültiges/fehlendes Datum → Hinweis statt 500
        archiv_date = _parse_date(request.form.get('tour_date'))
        if archiv_date is None:
            flash('Bitte ein gültiges Datum angeben.', 'danger')
            return redirect(url_for('archiv_new'))
        from flask import g as _g_archiv
        _grp_archiv = getattr(_g_archiv, 'group', None)
        tour = Tour(
            title        = title,
            description  = request.form.get('description', '').strip() or None,
            tour_date    = archiv_date,
            difficulty   = request.form.get('difficulty', 'mittel'),
            status       = 'completed',
            created_by   = current_user.id,
            meeting_desc = request.form.get('meeting_desc', '').strip() or None,
            group_id     = _grp_archiv.id if _grp_archiv else None,
        )
        tour.gpx_km     = _parse_float(request.form.get('gpx_km'))      # akzeptiert auch "42,5"
        tour.gpx_ascent = _parse_float(request.form.get('gpx_ascent'))
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
                    _tour_apply_gpx_metrics(tour, parsed)      # Build w
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

    # Build v: Jahresauswahl auch ohne Suche füllen; GPX-Zähler für den ZIP-Button
    gpx_total = q.filter(Tour.gpx_file != None).count()
    return render_template('touren/archiv.html', tours=tours,
                           part_counts=part_counts, photo_counts=photo_counts,
                           page=page, pages=pages, total=total,
                           cover_photos=cover_photos, all_years=_archiv_years(),
                           q='', year='', diff='', gpx_total=gpx_total)


@app.route('/hilfe')
@login_required
def hilfe():
    return render_template('hilfe.html')


# ─── Build aa: Live-Karte (Standorte der Mitfahrer) ────────────────────────────────────────────
LIVE_STALE_S = 15 * 60      # ohne neues Signal nach 15 Minuten ausgeblendet
LIVE_FRESH_S = 5 * 60       # „aktuell“ – zählt für die Spannweite der Gruppe


def _berlin_today():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Europe/Berlin')).date()


def _berlin_now():
    """Build ab: aktuelle Uhrzeit in Europe/Berlin (Server läuft in UTC)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Europe/Berlin'))
    except Exception:
        return datetime.now()


def _cfg_int(key, default, lo=None, hi=None):
    """Build ab: Ganzzahl aus SiteConfig mit Default und Wertebereich."""
    try:
        v = int(str(cfg(key) or '').strip())
    except (TypeError, ValueError):
        return default
    if lo is not None and v < lo:
        return default
    if hi is not None and v > hi:
        return default
    return v


def _set_day_flag(prefix, flag_key):
    """Build ab: Tagesflag (z. B. morning_reminder_sent_2026-10-14) setzen und ältere
    Flags mit demselben Präfix löschen – sonst sammelt sich in site_config pro Tag
    eine neue Zeile an. Commit macht der Aufrufer."""
    try:
        SiteConfig.query.filter(SiteConfig.key.like(prefix + '%'),
                                SiteConfig.key != flag_key).delete(synchronize_session=False)
    except Exception as e:
        app.logger.warning(f'Flag-Aufräumen {prefix}: {e}')
    SiteConfig.set(flag_key, '1')


def _initials(name):
    """„Hein Mück“ → „HM“, „Fiete“ → „FI“ – für die Marker auf der Live-Karte."""
    parts = [x for x in re.split(r'[\s\-]+', (name or '').strip()) if x]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _live_share_window(tour, user=None, today=None):
    """(erlaubt, Hinweis): Standort teilen geht vom Vortag bis einen Tag nach dem Tourtag; Organisatoren
    jederzeit (zum Ausprobieren und Vorführen). Zuschauen darf unabhängig davon jeder in der Gruppe."""
    user = user or current_user
    if tour.status == 'cancelled':
        return False, 'Die Tour ist abgesagt.'
    if getattr(user, 'is_organizer', False):
        return True, ''
    if tour.is_date_open:
        return False, 'Die Tour hat noch keinen Termin – Standort teilen geht ab dem Vortag der Tour.'
    delta = (tour.tour_date - (today or _berlin_today())).days
    if delta > 1:
        return False, f'Standort teilen geht ab dem Vortag der Tour (Tourtag: {tour.tour_date.strftime("%d.%m.%Y")}).'
    if delta < -1:
        return False, 'Die Tour liegt zurück – Standort teilen war bis einen Tag danach möglich.'
    return True, ''


def _live_locations_payload(tour_id, now=None):
    """Aktuelle Standorte einer Tour – eine Abfrage mit Nutzer-Join (vorher je Zeile ein User-Zugriff)."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=LIVE_STALE_S)
    rows = (db.session.query(LiveLocation, User)
            .join(User, User.id == LiveLocation.user_id)
            .filter(LiveLocation.tour_id == tour_id, LiveLocation.updated_at >= cutoff)
            .order_by(LiveLocation.updated_at.desc()).all())
    out = []
    for loc, u in rows:
        name = u.display_name if u else 'Unbekannt'
        out.append({'user_id': loc.user_id, 'name': name, 'initials': _initials(name),
                    'lat': loc.lat, 'lng': loc.lng, 'accuracy': loc.accuracy,
                    'speed': loc.speed, 'heading': loc.heading,
                    'ago': max(0, int((now - loc.updated_at).total_seconds()))})
    return out


def _live_cleanup(now=None):
    """Zeilen älter als ein Tag löschen (wird aus location_update gelegentlich aufgerufen)."""
    now = now or datetime.utcnow()
    n = LiveLocation.query.filter(LiveLocation.updated_at < now - timedelta(days=1)).delete(synchronize_session=False)
    return n


@app.route('/touren/<int:tour_id>/live')
@login_required
def tour_live(tour_id):
    """Build aa: schlanke Live-Karte einer Tour – Track, Treffpunkt, Einkehr und die Standorte der
    Mitfahrer. Zuschauen kann jeder in der Gruppe (Nachzügler, Daheimgebliebene), teilen im Zeitfenster
    um den Tourtag. Bewusst ohne Fotos/Videos/Kommentare: schnell geladen, große Knöpfe, Vollbild."""
    tour = _tour_or_404(tour_id)
    track = []
    if tour.gpx_file:
        path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
        if os.path.exists(path):
            try:
                pts = (parse_gpx(path) or {}).get('points') or []
                track = [[round(a, 5), round(b, 5)] for a, b in _simplify_track(pts, 600)]
            except Exception as e:
                app.logger.warning(f'Live-Karte Tour {tour_id}: GPX nicht lesbar: {e}')
    meeting = None
    if tour.meeting_lat and tour.meeting_lng:
        meeting = {'lat': tour.meeting_lat, 'lng': tour.meeting_lng, 'desc': tour.meeting_desc or 'Treffpunkt'}
    ek = _einkehr_info(tour)
    einkehr = None
    if ek and ek.get('lat') and ek.get('lng'):
        einkehr = {'lat': ek['lat'], 'lng': ek['lng'], 'name': ek['name'], 'url': ek['url'],
                   'hours': ek['hours'], 'lunch_label': ek.get('lunch_label', '')}
    can_share, share_hint = _live_share_window(tour)
    me_name = current_user.display_name
    me = {'id': current_user.id, 'name': me_name, 'initials': _initials(me_name)}
    datum = '' if tour.is_date_open else (['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][tour.tour_date.weekday()]
                                          + ', ' + tour.tour_date.strftime('%d.%m.%Y'))
    return render_template('touren/live.html', tour=tour, datum=datum,
                           track_json=_json_for_script(track), meeting_json=_json_for_script(meeting),
                           einkehr_json=_json_for_script(einkehr), me_json=_json_for_script(me),
                           locations_json=_json_for_script(_live_locations_payload(tour.id)),
                           can_share=can_share, share_hint=share_hint,
                           stale_s=LIVE_STALE_S, fresh_s=LIVE_FRESH_S)


@app.route('/api/location/update', methods=['POST'])
@login_required
def location_update():
    """Eigenen Live-Standort melden. Build aa: nur im Zeitfenster um den Tourtag (403 mit Hinweis),
    zusätzlich Tempo/Richtung, Antwort enthält gleich alle Standorte (spart dem Sender das Polling)."""
    data = request.get_json(silent=True) or {}
    tour_id  = data.get('tour_id')
    lat      = data.get('lat')
    lng      = data.get('lng')
    accuracy = data.get('accuracy')
    if tour_id is None or lat is None or lng is None:
        return jsonify({'error': 'missing data'}), 400
    try:                                                  # Audit 1.4.0: Zahlen erzwingen
        tour_id  = int(tour_id)
        lat, lng = float(lat), float(lng)
        accuracy = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid data'}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({'error': 'invalid coordinates'}), 400

    def _opt_float(v, lo, hi):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if lo <= f <= hi and f == f else None
    speed   = _opt_float(data.get('speed'), 0, 60)        # m/s
    heading = _opt_float(data.get('heading'), 0, 360)     # Grad
    tour = _tour_or_404(tour_id)
    ok, hint = _live_share_window(tour)
    if not ok:
        return jsonify({'error': hint}), 403
    now = datetime.utcnow()
    existing = LiveLocation.query.filter_by(tour_id=tour_id, user_id=current_user.id).first()
    if existing:
        existing.lat, existing.lng, existing.accuracy = lat, lng, accuracy
        existing.speed, existing.heading = speed, heading
        existing.updated_at = now
    else:
        db.session.add(LiveLocation(tour_id=tour_id, user_id=current_user.id, lat=lat, lng=lng,
                                    accuracy=accuracy, speed=speed, heading=heading, updated_at=now))
    import random
    if random.random() < 0.05:
        _live_cleanup(now)
    db.session.commit()
    return jsonify({'ok': True, 'locations': _live_locations_payload(tour_id, now)})


@app.route('/api/location/tour/<int:tour_id>')
@login_required
def location_get(tour_id):
    """Alle aktuellen Live-Standorte einer Tour (Polling der Live-Karte)."""
    _tour_or_404(tour_id)   # Audit 1.4.0: nur Touren der eigenen Gruppe
    return jsonify({'locations': _live_locations_payload(tour_id), 'stale_s': LIVE_STALE_S})


@app.route('/api/location/stop', methods=['POST'])
@login_required
def location_stop():
    """Eigenen Live-Standort entfernen – auch per sendBeacon beim Verlassen der Seite (dann steht die
    tour_id in der URL und der Body ist leer)."""
    data = request.get_json(silent=True) or {}
    raw = data.get('tour_id') or request.form.get('tour_id') or request.args.get('tour_id') or ''
    tour_id = _parse_int(str(raw))
    if not tour_id:
        return jsonify({'error': 'tour_id fehlt'}), 400
    LiveLocation.query.filter_by(tour_id=tour_id, user_id=current_user.id).delete()
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


_ZEITABSTIMMUNG_FALLBACK = """{% extends "base.html" %}
{% block title %}Startzeit abstimmen{% endblock %}
{% block content %}
<div class="mb-3"><a href="{{ url_for('tour_detail', tour_id=tour.id) }}" class="text-muted small">&larr; Zurück</a></div>
<h2 class="fw-bold mb-3" style="color:var(--djo-navy)">Startzeit abstimmen: {{ tour.title }}</h2>
<div class="card"><div class="card-body">
<form method="post">
  {% for slot in default_slots %}
  <div class="form-check mb-2">
    <input class="form-check-input" type="checkbox" name="slots" value="{{ slot }}" id="s{{ loop.index }}" {% if slot in my_votes %}checked{% endif %}>
    <label class="form-check-label" for="s{{ loop.index }}">{{ slot }} Uhr
      <span class="badge bg-secondary ms-1">{{ slot_counts.get(slot, 0) }} / {{ member_count }}</span>
      {% if slot_voters.get(slot) %}<small class="text-muted ms-1">{{ slot_voters[slot]|join(', ') }}</small>{% endif %}
    </label>
  </div>
  {% endfor %}
  <button class="btn btn-djo mt-2" type="submit">Speichern</button>
</form>
{% if current_user.is_organizer and slot_counts %}
<hr><form method="post" action="{{ url_for('tour_set_time_from_vote', tour_id=tour.id) }}" class="d-flex gap-2 align-items-center">
  <select name="slot" class="form-select form-select-sm w-auto">{% for slot, n in slot_counts.most_common() %}<option value="{{ slot }}">{{ slot }} ({{ n }})</option>{% endfor %}</select>
  <button class="btn btn-sm btn-outline-secondary" type="submit">Beste Zeit übernehmen</button>
</form>{% endif %}
</div></div>
{% endblock %}"""


@app.route('/touren/<int:tour_id>/zeitabstimmung', methods=['GET', 'POST'])
@login_required
def tour_time_vote(tour_id):
    """Startzeit-Abstimmung für geplante Touren."""
    tour = _tour_or_404(tour_id)
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

    _tpl = 'touren/zeitabstimmung.html'
    try:
        app.jinja_env.get_or_select_template(_tpl)
    except Exception:
        _tpl = None
    if _tpl is None:
        return render_template_string(_ZEITABSTIMMUNG_FALLBACK,
                           tour=tour, my_votes=my_votes,
                           slot_counts=slot_counts, slot_voters=slot_voters,
                           default_slots=default_slots,
                           member_count=member_count)
    return render_template(_tpl,
                           tour=tour, my_votes=my_votes,
                           slot_counts=slot_counts, slot_voters=slot_voters,
                           default_slots=default_slots,
                           member_count=member_count)


@app.route('/touren/<int:tour_id>/zeitabstimmung/setzen', methods=['POST'])
@login_required
@organizer_required
def tour_set_time_from_vote(tour_id):
    """Beste Startzeit aus Abstimmung übernehmen."""
    tour = _tour_or_404(tour_id)
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
    _tour_or_404(tour_id)
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
    tour = _tour_or_404(tour_id)
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

    comments = (TourComment.query.join(Tour, TourComment.tour_id == Tour.id)
                .filter(TourComment.content.ilike(like))
                .filter(Tour.id.in_(_gq(Tour).with_entities(Tour.id)))
                .order_by(TourComment.created_at.desc())
                .limit(10).all())

    photo_hits = (TourPhoto.query.join(Tour, TourPhoto.tour_id == Tour.id)
                  .filter(TourPhoto.caption.ilike(like),
                          TourPhoto.caption != None)
                  .filter(Tour.id.in_(_gq(Tour).with_entities(Tour.id)))
                  .limit(8).all())

    video_hits = (TourVideo.query
                  .join(Tour, TourVideo.tour_id == Tour.id)
                  .filter(TourVideo.title.ilike(like))
                  .filter(Tour.id.in_(_gq(Tour).with_entities(Tour.id)))
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


def _safe_extractall(tf, dest):
    """Build ab: tar-Archiv entpacken, aber nur reguläre Dateien/Ordner mit relativen
    Pfaden innerhalb von dest – keine absoluten Pfade, kein „..“, keine Symlinks/Geräte.
    (Python 3.12 bringt dafür filter='data' mit; der Server hat 3.11.)"""
    dest_real = os.path.realpath(dest)
    safe = []
    for m in tf.getmembers():
        if not (m.isfile() or m.isdir()):
            continue
        name = m.name.replace('\\', '/')
        if name.startswith('/') or '..' in name.split('/'):
            continue
        target = os.path.realpath(os.path.join(dest_real, name))
        if target != dest_real and not target.startswith(dest_real + os.sep):
            continue
        safe.append(m)
    tf.extractall(dest, members=safe)


def _rotate_backups():
    """Räumt alte Backups nach Generationen-Prinzip auf:
    - letzte 7 Tage: alle behalten
    - letzte 8 Wochen: eine pro Woche behalten
    - letzte 12 Monate: eine pro Monat behalten
    - älter: gelöscht
    Erwartet Dateinamen mit Datum, z.B. backup_2026-05-12_...  – Dateien ohne
    erkennbares Datum werden nicht angefasst (sicherer Default).
    Build ab: Komplett-Backups (djo_backup_), Datenbank-Backups (djo_db_) und
    sonstige Dateien werden getrennt rotiert, damit nicht ein kleines DB-Backup
    den Wochen-/Monatsplatz des Komplett-Backups belegt.
    """
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    if not os.path.isdir(backup_dir):
        return 0
    import re as _re
    date_re = _re.compile(r'(\d{4}-\d{2}-\d{2})')
    groups = {'djo_backup_': [], 'djo_db_': [], '': []}
    for fname in os.listdir(backup_dir):
        fpath = os.path.join(backup_dir, fname)
        if not os.path.isfile(fpath):
            continue
        m = date_re.search(fname)
        if not m:
            continue
        try:
            fdate = datetime.strptime(m.group(1), '%Y-%m-%d').date()
        except ValueError:
            continue
        key = next((k for k in ('djo_backup_', 'djo_db_') if fname.startswith(k)), '')
        groups[key].append((fdate, fname, fpath))
    deleted = 0
    for entries in groups.values():
        if entries:
            deleted += _rotate_backup_entries(entries)
    return deleted


def _rotate_backup_entries(entries):
    """Generationen-Rotation für eine Liste (datum, name, pfad); liefert gelöschte Anzahl."""
    entries.sort(key=lambda x: x[0], reverse=True)

    today = date.today()
    keep = set()
    seen_weeks = set()
    seen_months = set()
    for fdate, fname, fpath in entries:
        age_days = (today - fdate).days
        if age_days <= 7:
            keep.add(fname)
        elif age_days <= 56:  # 8 Wochen
            wk = fdate.isocalendar()[:2]  # (Jahr, KW)
            if wk not in seen_weeks:
                seen_weeks.add(wk)
                keep.add(fname)
        elif age_days <= 365:  # 12 Monate
            mk = (fdate.year, fdate.month)
            if mk not in seen_months:
                seen_months.add(mk)
                keep.add(fname)
        # älter als 365 Tage: nicht behalten

    deleted = 0
    for fdate, fname, fpath in entries:
        if fname not in keep:
            try:
                os.remove(fpath)
                deleted += 1
            except Exception:
                pass
    return deleted


_backup_lock = __import__('threading').Lock()   # Build ab: nie zwei Backups gleichzeitig (pro Prozess)


def _run_backup(triggered_by='manuell', mode='full'):
    """Führt backup.sh aus und protokolliert Zeitpunkt/Ergebnis in SiteConfig.
    Gibt (erfolgreich: bool, meldung: str) zurück.
    Build ab: mode='full' = Datenbank + Fotos/GPX (Videos nur, wenn die Einstellung
    backup_include_videos aktiv ist), mode='db' = nur die Datenbank (klein, täglich)."""
    import subprocess
    backup_script = os.path.join(os.path.dirname(__file__), 'backup.sh')
    if not os.path.exists(backup_script):
        return False, 'backup.sh nicht gefunden.'
    if mode not in ('full', 'db'):
        mode = 'full'
    if not _backup_lock.acquire(blocking=False):
        return False, 'Ein Backup läuft bereits – bitte kurz warten.'
    try:
        env = dict(os.environ, INCLUDE_VIDEOS='1' if cfg('backup_include_videos') == '1' else '0')
        result = subprocess.run(
            ['bash', backup_script, mode],
            capture_output=True, text=True, timeout=600 if mode == 'full' else 120, env=env
        )
        now_iso = datetime.utcnow().isoformat()
        if result.returncode == 0:
            SiteConfig.set('backup_last_run', now_iso)
            SiteConfig.set('backup_last_status', 'ok')
            SiteConfig.set('backup_last_trigger', triggered_by)
            SiteConfig.set('backup_last_mode', mode)
            SiteConfig.set('backup_last_db_run', now_iso)
            if mode == 'full':
                SiteConfig.set('backup_last_full_run', now_iso)
            db.session.commit()
            msg = result.stdout.strip() or 'Backup erstellt.'
            # Alte Backups nach Generationen-Prinzip aufräumen
            try:
                deleted = _rotate_backups()
                if deleted:
                    msg += f' ({deleted} alte Backup(s) aufgeräumt.)'
            except Exception as e:
                app.logger.warning(f'Backup-Rotation Fehler: {e}')
            # Optionale E-Mail-Benachrichtigung bei automatischem Lauf
            if triggered_by != 'manuell' and cfg('backup_notify_email') == '1':
                admin_mail = cfg('admin_email')
                if admin_mail:
                    try:
                        send_mail(to=admin_mail, subject='✅ Backup erfolgreich – De jungen Olen',
                                  body=f'Automatisches Backup ({triggered_by}) wurde erstellt.\n\n{msg}')
                    except Exception:
                        pass
            return True, msg
        else:
            SiteConfig.set('backup_last_run', now_iso)
            SiteConfig.set('backup_last_status', 'error')
            SiteConfig.set('backup_last_trigger', triggered_by)
            SiteConfig.set('backup_last_mode', mode)
            db.session.commit()
            err = (result.stderr or result.stdout or '')[:300]
            if triggered_by != 'manuell' and cfg('backup_notify_email') == '1':
                admin_mail = cfg('admin_email')
                if admin_mail:
                    try:
                        send_mail(to=admin_mail, subject='❌ Backup fehlgeschlagen – De jungen Olen',
                                  body=f'Automatisches Backup ({triggered_by}) ist fehlgeschlagen:\n\n{err}')
                    except Exception:
                        pass
            return False, f'Backup-Fehler: {err}'
    except Exception as e:
        return False, f'Backup fehlgeschlagen: {e}'
    finally:
        _backup_lock.release()


def _backup_is_due():
    """Prüft anhand der Einstellungen, ob ein automatisches Backup fällig ist.
    Build ab: liefert den fälligen Modus – 'full' (Datenbank + Uploads, nach dem
    eingestellten Intervall), 'db' (nur Datenbank, täglich) oder None.
    Komplett-Backups werden ab backup_last_full_run gerechnet; fehlt der Wert
    (ältere Installation), zählt backup_last_run."""
    interval = cfg('backup_interval') or 'off'
    if interval == 'off':
        return None

    def _elapsed(key, fallback=None):
        raw = cfg(key) or (cfg(fallback) if fallback else None)
        if not raw:
            return None
        try:
            return datetime.utcnow() - datetime.fromisoformat(raw)
        except ValueError:
            return None

    thresholds = {
        'daily':   timedelta(hours=23),
        'weekly':  timedelta(days=6, hours=23),
        'monthly': timedelta(days=27),
    }
    full_gap = _elapsed('backup_last_full_run', 'backup_last_run')
    if full_gap is None or full_gap >= thresholds[interval]:
        return 'full'
    db_gap = _elapsed('backup_last_db_run', 'backup_last_run')
    if db_gap is None or db_gap >= timedelta(hours=23):
        return 'db'
    return None


def _start_backup_in_background(mode, triggered_by='auto'):
    """Build ab: automatisches Backup in einem Hintergrund-Thread, damit der auslösende
    Seitenaufruf nicht mehrere Sekunden (bei großen Foto-Ordnern Minuten) hängt.
    Der Lock in _run_backup verhindert parallele Läufe; läuft schon eines, passiert nichts."""
    import threading

    def _worker():
        with app.app_context():
            try:
                ok, msg = _run_backup(triggered_by=triggered_by, mode=mode)
                app.logger.info(f'Hintergrund-Backup ({mode}, {triggered_by}): {"ok" if ok else "FEHLER"} – {msg}')
            except Exception as e:
                app.logger.warning(f'Hintergrund-Backup Fehler: {e}')
            finally:
                db.session.remove()

    if _backup_lock.locked():
        return False
    threading.Thread(target=_worker, name=f'djo-backup-{mode}', daemon=True).start()
    return True


@app.route('/admin/backup', methods=['POST'])
@login_required
def admin_backup():
    """Manuelles Backup aus dem Admin-Dashboard."""
    if not current_user.is_admin:
        abort(403)
    mode = 'db' if request.form.get('mode') == 'db' else 'full'    # Build ab
    ok, msg = _run_backup(triggered_by='manuell', mode=mode)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('admin_backups_list'))


# ─── Admin routes ─────────────────────────────────────────────────────────────
# Pakete, die der Admin ohne SSH nachinstallieren/reparieren kann (alle in requirements.txt).
# (pip-Name, Beschreibung, Modul für die Prüfung)
_INSTALLABLE_PACKAGES = (
    ('Pillow',       'Bildverarbeitung: Foto-Resize, Avatare, Video-Titel/Blur-Hintergrund (sonst ImageMagick-Fallback)', 'PIL'),
    ('piexif',       'EXIF/GPS lesen – zweite Methode nach dem eingebauten Parser (exif_gps.py)', 'piexif'),
    ('cryptography', 'Push-Benachrichtigungen (VAPID-Schlüssel)', 'cryptography.hazmat.primitives.asymmetric.ec'),
    ('pywebpush',    'Push-Benachrichtigungen (Web Push)', 'pywebpush'),
)


def _package_status(module):
    """Importprüfung für die Admin-Seite: {'ok', 'status', 'detail'} mit status
    installiert | fehlt | defekt. Pillow wird funktional geprüft (C-Erweiterung _imaging),
    weil ein für eine andere Python-Version gebautes Pillow (z. B. 3.9 nach dem Update auf
    3.11) zwar importierbar aussieht, aber nicht arbeitet."""
    import sys, importlib
    top = module.split('.')[0]
    try:
        m = importlib.import_module(module)
        pkg = sys.modules.get(top, m)
        ver = getattr(pkg, '__version__', '')
        loc = os.path.dirname(getattr(pkg, '__file__', '') or '')
        if top == 'PIL' and not _pillow_ok():
            return {'ok': False, 'status': 'defekt',
                    'detail': f'{loc} – C-Erweiterung „_imaging“ lädt nicht (für eine andere Python-Version gebaut)'}
        return {'ok': True, 'status': 'installiert', 'detail': f'{ver} – {loc}'.strip(' –')}
    except ModuleNotFoundError as e:
        if (e.name or '').split('.')[0] == top:
            return {'ok': False, 'status': 'fehlt', 'detail': ''}
        return {'ok': False, 'status': 'defekt', 'detail': f'{type(e).__name__}: {str(e)[:160]}'}
    except Exception as e:   # ImportError einer kaputten C-Erweiterung u. ä.
        return {'ok': False, 'status': 'defekt', 'detail': f'{type(e).__name__}: {str(e)[:160]}'}


def _pip_install(pkg, target):
    """pip-Installation mit mehreren Strategien (ohne SSH). Liefert (ok, log).
    1. --target <site-packages der App> (--upgrade ersetzt kaputte Reste; umgeht die
       Debian-12-Sperre „externally-managed-environment“)
    2. --user   3. --user --break-system-packages
    Fehlt pip für diesen Interpreter ganz, wird einmalig ensurepip versucht."""
    import sys
    base = [sys.executable, '-m', 'pip', 'install', '--upgrade', '--quiet', pkg]
    strategies = ([base + ['--target', target]] if target else []) + \
                 [base + ['--user'], base + ['--user', '--break-system-packages']]
    log, tried_ensurepip = '', False
    for cmd in strategies:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        except Exception as e:
            log += '$ ' + ' '.join(cmd[2:]) + '\n' + str(e)[:300] + '\n'
            continue
        if r.returncode == 0:
            return True, ''
        err = (r.stderr or r.stdout or '')[-600:]
        log += '$ ' + ' '.join(cmd[2:]) + '\n' + err + '\n'
        if 'No module named pip' in err and not tried_ensurepip:
            tried_ensurepip = True
            try:
                e = subprocess.run([sys.executable, '-m', 'ensurepip', '--user', '--upgrade'],
                                   capture_output=True, text=True, timeout=120)
                log += '$ ensurepip --user\n' + (e.stderr or e.stdout or '')[-300:] + '\n'
                if e.returncode == 0:
                    r2 = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
                    if r2.returncode == 0:
                        return True, ''
                    log += '$ ' + ' '.join(cmd[2:]) + '\n' + (r2.stderr or r2.stdout or '')[-600:] + '\n'
            except Exception as ex:
                log += '$ ensurepip\n' + str(ex)[:300] + '\n'
    return False, log


@app.route('/admin/install-packages', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_install_packages():
    """Python-Pakete ohne SSH prüfen, nachinstallieren oder reparieren."""
    import sys, importlib
    # Ziel-Pfad: der venv-Ordner der schon in sys.path ist. Audit 1.4.0: Pfade einer
    # anderen Python-Version (z. B. ".../python3.9/..." nach dem Update auf 3.11) überspringen.
    _pyver = 'python{}.{}'.format(sys.version_info.major, sys.version_info.minor)
    venv_target = next(
        (p for p in sys.path if 'site-packages' in p and os.path.isdir(p)
         and (_pyver in p or not re.search(r'python3\.\d+', p))),
        None
    )

    # Umgebungs-Diagnose (ohne SSH prüfbar)
    import shutil as _sh
    py_info = {'version': sys.version.split()[0], 'executable': sys.executable}
    try:
        r = subprocess.run([sys.executable, '-m', 'pip', '--version'],
                           capture_output=True, text=True, timeout=30)
        py_info['pip'] = (r.stdout.strip() if r.returncode == 0
                          else 'nicht verfügbar – ' + (r.stderr or r.stdout).strip()[-160:])
    except Exception as e:
        py_info['pip'] = f'nicht prüfbar – {str(e)[:120]}'
    g = _package_status('gpxpy')
    py_info['gpxpy (GPX)'] = ('OK – ' if g['ok'] else g['status'] + ' – ') + g['detail']
    py_info['ImageMagick (Fallback)'] = _sh.which('convert') or _sh.which('magick') or 'nicht gefunden'

    results = []
    if request.method == 'POST':
        wanted = set(request.form.getlist('pkg'))
        if not wanted:
            flash('Kein Paket ausgewählt.', 'info')
        installed_any = False
        for pip_name, desc, module in _INSTALLABLE_PACKAGES:
            st = _package_status(module)
            row = {'pkg': pip_name, 'desc': desc, 'module': module, **st, 'log': ''}
            if pip_name in wanted:
                ok, log = _pip_install(pip_name, venv_target)
                if ok:
                    installed_any = True
                    # Prüfung mit den neuen Dateien wiederholen: nur Module verwerfen,
                    # die vorher fehlten/defekt waren (intakte C-Erweiterungen nicht neu laden).
                    top = module.split('.')[0]
                    if not st['ok']:
                        for name in [n for n in sys.modules if n == top or n.startswith(top + '.')]:
                            del sys.modules[name]
                    importlib.invalidate_caches()
                    st2 = _package_status(module)
                    row.update(st2)
                    row['status'] = 'installiert' if st2['ok'] else st2['status'] + ' (trotz Installation)'
                    row['action'] = 'installiert'
                else:
                    row['action'] = 'fehlgeschlagen'
                    row['log'] = log
            results.append(row)
        failed = [r for r in results if r.get('action') == 'fehlgeschlagen']
        if wanted:
            flash('Installation fehlgeschlagen – Details unten.' if failed else
                  'Installation abgeschlossen.' + (' Bitte die App einmal neu starten (Plesk → Restart), '
                                                  'damit alle Prozesse die neuen Pakete nutzen.' if installed_any else ''),
                  'warning' if failed else 'success')
    else:
        for pip_name, desc, module in _INSTALLABLE_PACKAGES:
            results.append({'pkg': pip_name, 'desc': desc, 'module': module, 'log': '',
                            **_package_status(module)})

    return render_template('admin/install_packages.html',
                           results=results, venv_target=venv_target, py_info=py_info)


@app.route('/admin/')
@login_required
@admin_required
def admin_dashboard():
    from datetime import timedelta
    # anonymisierte (gelöschte) Konten nicht mehr anzeigen
    users   = (_gq(User).filter(~User.email.like('%@deleted.local'))
               .order_by(User.created_at).all())
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

    backup_last_run_str = cfg('backup_last_run')
    backup_last_run = None
    if backup_last_run_str:
        try:
            backup_last_run = datetime.fromisoformat(backup_last_run_str)
        except ValueError:
            pass

    invite_texts = {i.id: _invite_text(i) for i in invites if not i.used}
    highlight_invite = request.args.get('invite', type=int)
    return render_template('admin/dashboard.html',
                           invite_texts=invite_texts,
                           highlight_invite=highlight_invite,
                           users=users, invites=invites,
                           active_users=active_users,
                           inactive_users=inactive_users,
                           birthdays=birthdays,
                           backup_last_run=backup_last_run,
                           backup_last_status=cfg('backup_last_status'),
                           backup_last_trigger=cfg('backup_last_trigger'),
                           backup_interval=cfg('backup_interval') or 'off',
                           backup_notify_email=cfg('backup_notify_email') or '0')


def _invite_text(inv):
    """WhatsApp-Einladungstext für einen Einladungslink."""
    from flask import g as _gi
    grp = getattr(_gi, 'group', None)
    gname = grp.name if grp else 'De jungen Olen'
    url = url_for('register', token=inv.token, _external=True)
    name = (inv.label or '').strip()
    bike = '\U0001F6B4'          # Radfahrer-Emoji (als Escape, unabhängig von Datei-Kodierung)
    point = '\U0001F449'         # Zeigefinger-Emoji
    hello = f'Hallo {name}! {bike}' if name else f'Hallo! {bike}'
    return (f'{hello}\n'
            f'Ich lade dich zu „{gname}“ ein – unserer Radgruppe. '
            f'Dort findest du alle Touren und Termine, Fotos und die Tourplanung an einem Ort.\n\n'
            f'{point} Hier kannst du dich registrieren:\n{url}\n\n'
            f'Der Link ist nur für dich gedacht. Bis bald auf dem Rad!')


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
    from flask import g as _g_invite
    _grp_invite = getattr(_g_invite, 'group', None)
    invite = InviteToken(token=token, email=email or None,
                         label=label or None, created_by=current_user.id,
                         group_id=_grp_invite.id if _grp_invite else None)
    db.session.add(invite)
    db.session.commit()
    invite_url = url_for('register', token=token, _external=True)
    label_str  = f' für {label}' if label else ''
    flash(f'Einladungslink{label_str} erstellt.', 'success')
    return redirect(url_for('admin_dashboard', invite=invite.id) + '#einladung')


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
    user = _own_group_or_404(User.query.get_or_404(user_id))   # Audit 1.4.0: nur eigene Gruppe
    if user.id == current_user.id:
        flash('Du kannst dich nicht selbst löschen.', 'warning')
        return redirect(url_for('admin_dashboard'))
    # Audit 1.4.0: Hartes Löschen scheiterte mit IntegrityError (NOT NULL in
    # tour_participants), sobald der Nutzer je an einer Tour teilgenommen hatte.
    # Stattdessen – wie beim DSGVO-Selbstlöschen – anonymisieren: Historie
    # (Teilnahmen, Fotos, Ranglisten der anderen) bleibt konsistent.
    name = user.name
    _anonymize_user(user)
    db.session.commit()
    flash(f'Benutzer {name} wurde entfernt (Konto anonymisiert und gesperrt).', 'success')
    return redirect(url_for('admin_dashboard'))


def _anonymize_user(user):
    """Persönliche Daten eines Nutzers entfernen, Datensatz für die Historie behalten."""
    if user.avatar:
        try:
            path = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], user.avatar)
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    user.name          = f'Gelöschter Nutzer {user.id}'
    user.nickname      = None
    user.email         = f'deleted_{user.id}@deleted.local'
    user.password_hash = secrets.token_hex(32)
    user.is_active     = False
    user.role          = 'member'
    user.avatar        = None
    user.bio           = None
    user.birthday      = None
    # Geräte-/Standortdaten und offene Reset-Links gehören niemandem mehr
    for model in (PushSubscription, LiveLocation, PasswordReset, TourRide):
        try:
            model.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        except Exception as e:
            app.logger.warning(f'anonymize cleanup {model.__name__}: {e}')


# ─── Phase 2: Gastronomie ─────────────────────────────────────────────────────

GASTRO_TYPES = [
    ('cafe',       '☕ Café'),
    ('baeckerei',  '🥐 Bäckerei'),
    ('kneipe',     '🍺 Kneipe / Gasthaus'),
    ('restaurant', '🍽️ Restaurant'),
    ('imbiss',     '🥪 Imbiss / Kiosk'),
    ('other',      '📍 Sonstiges'),
]

_OH_DAYS_EN = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
_OH_DAYS_DE = {'Mo': 'Mo', 'Tu': 'Di', 'We': 'Mi', 'Th': 'Do', 'Fr': 'Fr', 'Sa': 'Sa', 'Su': 'So',
               'PH': 'Feiertag', 'SH': 'Schulferien'}
_DE_DAY_WORDS = {'montag': 'Mo', 'dienstag': 'Di', 'mittwoch': 'Mi', 'donnerstag': 'Do', 'freitag': 'Fr',
                 'samstag': 'Sa', 'sonnabend': 'Sa', 'sonntag': 'So',
                 'mo': 'Mo', 'di': 'Di', 'mi': 'Mi', 'do': 'Do', 'fr': 'Fr', 'sa': 'Sa', 'so': 'So'}
_DE_DAYTOK = r'(?:Montags?|Dienstags?|Mittwochs?|Donnerstags?|Freitags?|Samstags?|Sonnabends?|Sonntags?|Mo|Di|Mi|Do|Fr|Sa|So)\.?'
_DE_DAYLIST = rf'{_DE_DAYTOK}(?:\s*(?:,|\+|&|/|und|bis|-|–)\s*{_DE_DAYTOK})*'


@app.template_filter('hours_de')
def hours_de(text):
    """Build t: OSM-opening_hours lesbar machen – „Mo-Fr 08:00-18:00; Sa 08:00-13:00; Su off“ →
    „Mo–Fr 08:00–18:00 · Sa 08:00–13:00 · So geschlossen“. Deutscher Freitext bleibt unverändert."""
    if not text:
        return ''
    out = str(text)
    out = re.sub(r'\b(Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)\b', lambda m: _OH_DAYS_DE[m.group(1)], out)
    out = re.sub(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', r'\1–\2', out)
    out = re.sub(r'\b(Mo|Di|Mi|Do|Fr|Sa|So)-(Mo|Di|Mi|Do|Fr|Sa|So)\b', r'\1–\2', out)
    out = re.sub(r'\b(off|closed)\b', 'geschlossen', out)
    out = out.replace('24/7', 'rund um die Uhr').replace('||', ' oder ')
    out = re.sub(r'\s*;\s*', ' · ', out)
    return out.strip(' ·')


def _expand_day_range(a, b):
    ia, ib = _OH_DAYS_EN.index(a), _OH_DAYS_EN.index(b)
    return _OH_DAYS_EN[ia:ib + 1] if ia <= ib else _OH_DAYS_EN[ia:] + _OH_DAYS_EN[:ib + 1]


@app.template_filter('closed_days')
def closed_days(text):
    """Build t: Ruhetage als Liste deutscher Kürzel, best effort – aus OSM („Mo off“, „Mo,Tu off“,
    „Mo-We off“) oder deutschem Freitext („Montag Ruhetag“, „Ruhetag: Mo + Di“, „Di geschlossen“)."""
    if not text:
        return []
    days = []
    for rule in re.split(r'[;|]+', str(text)):
        r = rule.strip()
        if not r:
            continue
        m = re.match(r'^((?:(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)'
                     r'(?:\s*,\s*(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)*)\s*(?:,\s*PH\s*)?(?:off|closed)\b', r)
        if m:
            for part in re.split(r'\s*,\s*', m.group(1)):
                if '-' in part:
                    a, b = part.split('-', 1)
                    days += [_OH_DAYS_DE[x] for x in _expand_day_range(a, b)]
                else:
                    days.append(_OH_DAYS_DE[part])
            continue
        found = re.findall(rf'\b({_DE_DAYLIST})\s*(?:ist\s+|=\s*)?(?:Ruhetag|geschlossen|zu)\b', r, re.I) + \
                re.findall(rf'Ruhetage?\s*:?\s*({_DE_DAYLIST})(?![a-zäöü])', r, re.I)
        for lst in found:
            toks = [t.rstrip('.') for t in re.findall(_DE_DAYTOK, lst, re.I)]
            codes = [_DE_DAY_WORDS.get(t.lower().rstrip('s') if len(t) > 3 else t.lower()) for t in toks]
            if len(toks) == 2 and re.search(r'\b(bis)\b|[-–]', lst) and codes[0] in _OH_DAYS_DE.values() and codes[1] in _OH_DAYS_DE.values():
                inv = {v: k for k, v in _OH_DAYS_DE.items() if k in _OH_DAYS_EN}
                codes = [_OH_DAYS_DE[x] for x in _expand_day_range(inv[codes[0]], inv[codes[1]])]
            days += [c for c in codes if c]
    seen = []
    for d in days:
        if d and d not in seen:
            seen.append(d)
    return seen


# ─── Build z: Mittagstisch – Öffnungszeiten je Wochentag auswerten ─────────────────────────────
_OH_DE2EN = {'Mo': 'Mo', 'Di': 'Tu', 'Mi': 'We', 'Do': 'Th', 'Fr': 'Fr', 'Sa': 'Sa', 'So': 'Su'}
_OH_TOKEN = re.compile(
    r'(?P<sep>;)'
    r'|(?P<allday>24/7)'
    r'|(?P<time>(?<!\d)(?P<h1>\d{1,2})(?:[:.](?P<m1>\d{2}))?\s*-\s*(?P<h2>\d{1,2})(?:[:.](?P<m2>\d{2}))?(?!\d))'
    r'|(?P<open>(?<!\d)(?P<h3>\d{1,2})(?:[:.](?P<m3>\d{2}))?\+)'
    r'|(?P<days>\b(?P<d1>Mo|Tu|We|Th|Fr|Sa|Su)\b(?:\s*-\s*\b(?P<d2>Mo|Tu|We|Th|Fr|Sa|Su)\b)?)'
    r'|(?P<off>\b(?i:off|closed|geschlossen|ruhetag)\b)'
    r'|(?P<hol>\b(?:PH|SH)\b)')
_LUNCH_SUB_DE = {'menu': 'Mittagsmenü', 'buffet': 'Buffet', 'specials': 'Tagesgerichte', 'tourist_menu': 'Touristenmenü'}
_CUISINE_DE = {'german': 'deutsch', 'regional': 'regional', 'local': 'regional', 'italian': 'italienisch', 'pizza': 'Pizza',
               'pasta': 'Pasta', 'greek': 'griechisch', 'burger': 'Burger', 'kebab': 'Döner', 'turkish': 'türkisch',
               'asian': 'asiatisch', 'chinese': 'chinesisch', 'thai': 'thailändisch', 'vietnamese': 'vietnamesisch',
               'indian': 'indisch', 'sushi': 'Sushi', 'japanese': 'japanisch', 'fish': 'Fisch', 'seafood': 'Fisch & Meeresfrüchte',
               'steak_house': 'Steakhaus', 'international': 'international', 'bavarian': 'bayrisch', 'austrian': 'österreichisch',
               'french': 'französisch', 'spanish': 'spanisch', 'tapas': 'Tapas', 'mexican': 'mexikanisch', 'american': 'amerikanisch',
               'coffee_shop': 'Kaffee & Kuchen', 'cake': 'Kuchen', 'ice_cream': 'Eis', 'breakfast': 'Frühstück',
               'sausage': 'Wurst', 'friture': 'Frittiertes', 'chicken': 'Hähnchen', 'bistro': 'Bistro', 'crepe': 'Crêpes',
               'pancake': 'Pfannkuchen', 'vegetarian': 'vegetarisch', 'vegan': 'vegan', 'barbecue': 'Grill',
               'fine_dining': 'gehobene Küche', 'bakery': 'Backwaren', 'sandwich': 'Sandwiches', 'noodle': 'Nudeln',
               'balkan': 'Balkan', 'croatian': 'kroatisch', 'portuguese': 'portugiesisch', 'frisian': 'friesisch',
               'lunch': 'Mittagstisch', 'soup': 'Suppen', 'potato': 'Kartoffelgerichte', 'dumplings': 'Klöße'}


def _oh_normalize(text):
    """Deutschen Öffnungszeiten-Freitext in die OSM-Schreibweise überführen (Tagesnamen, „bis“, „Uhr“,
    „täglich“, „Feiertag“, „Ruhetag:“), damit _oh_week() beides mit einem Tokenizer lesen kann."""
    s = str(text).replace('–', '-').replace('—', '-').replace('−', '-').replace('||', ';')
    s = re.sub(r'(\d)\s*h\b', r'\1 ', s, flags=re.I)                  # „9h–18h“
    s = re.sub(r'\bUhr\b', ' ', s, flags=re.I)
    s = re.sub(r'\b(?:täglich|taeglich|daily|jeden Tag|alle Tage)\b', 'Mo-Su', s, flags=re.I)
    s = re.sub(r'\bbis\b', '-', s, flags=re.I)
    s = re.sub(r'\b(montags?|dienstags?|mittwochs?|donnerstags?|freitags?|samstags?|sonnabends?|sonntags?)\b',
               lambda m: _OH_DE2EN[_DE_DAY_WORDS[m.group(1).lower().rstrip('s')]], s, flags=re.I)
    s = re.sub(r'\b(Di|Mi|Do|So)\b\.?', lambda m: _OH_DE2EN[m.group(1)], s)
    s = re.sub(r'\bFeiertage?n?s?\b', 'PH', s, flags=re.I)
    s = re.sub(r'\bRuhetage?\s*:\s*', 'Ruhetag ', s, flags=re.I)
    return s


def _oh_week(text):
    """Build z: Öffnungszeiten (OSM-opening_hours oder deutscher Kurztext) → Dict Wochentag (0 = Mo … 6 = So)
    → Liste offener Zeitfenster in Minuten [(start, ende), …]; [] = geschlossen, None = keine Angabe.
    Spätere Regeln überschreiben frühere (OSM-Semantik); nennt eine Regel mit Uhrzeit ausdrücklich Tage,
    gelten nicht genannte Tage als geschlossen. Rückgabe None, wenn nichts Verwertbares erkannt wurde."""
    if not text:
        return None
    s = _oh_normalize(text)
    groups = []

    def new():
        return {'days': [], 'times': [], 'off': False, 'hol': False, 'explicit': True}

    def flush(g):
        if not (g['times'] or g['off']):
            if g['days'] and not g['hol']:
                g['times'] = [(0, 1440)]            # „Di-So“ ohne Uhrzeit: geöffnet, Zeiten unbekannt
            else:
                return
        if not g['days']:
            if g['hol']:
                return                              # „PH off“: betrifft nur Feiertage
            g['days'] = list(range(7))
            g['explicit'] = False
        groups.append(g)

    g = new()
    for m in _OH_TOKEN.finditer(s):
        kind = m.lastgroup
        if kind == 'sep':
            flush(g); g = new()
        elif kind == 'hol':
            g['hol'] = True
        elif kind == 'days':
            if g['days'] and (g['times'] or g['off']):  # „Mo-Fr 9-18, Sa 9-13“: neue Gruppe in derselben Regel
                flush(g); g = new()
            a = _OH_DAYS_EN.index(m.group('d1'))
            if m.group('d2'):
                b = _OH_DAYS_EN.index(m.group('d2'))
                rng = list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
            else:
                rng = [a]
            g['days'] += [d for d in rng if d not in g['days']]
        elif kind == 'off':
            g['off'] = True
            g['times'] = []
        elif kind == 'allday':
            g['times'].append((0, 1440))
        elif kind == 'open':
            h, mi = int(m.group('h3')), int(m.group('m3') or 0)
            if h <= 24 and mi < 60:
                g['times'].append((h * 60 + mi, 1440))
        else:                                       # time
            h1, m1 = int(m.group('h1')), int(m.group('m1') or 0)
            h2, m2 = int(m.group('h2')), int(m.group('m2') or 0)
            if h1 > 24 or h2 > 24 or m1 >= 60 or m2 >= 60:
                continue
            a, b = h1 * 60 + m1, h2 * 60 + m2
            if b <= a:
                b += 1440                           # über Mitternacht
            g['times'].append((a, b))
    flush(g)
    if not groups:
        return None
    week = {i: None for i in range(7)}
    for x in groups:
        for d in x['days']:
            week[d] = [] if x['off'] else list(x['times'])
    if any(x['explicit'] and not x['off'] for x in groups):
        for d in range(7):
            if week[d] is None:
                week[d] = []
    return week


def noon_days(text, kitchen=None):
    """Build z: Wochentage (OSM-Kürzel Mo…Su), an denen laut Öffnungszeiten mittags geöffnet ist –
    um 12:45 Uhr offen und mindestens 60 Minuten zwischen 12 und 14 Uhr. Küchenzeiten
    (opening_hours:kitchen) gehen vor, wenn lesbar. None = keine Uhrzeiten erkennbar."""
    week = _oh_week(kitchen) if kitchen else None
    if not week or not any(week.values()):
        week = _oh_week(text)
    if not week or not any(week.values()):
        return None
    out = []
    for i, code in enumerate(_OH_DAYS_EN):
        for a, b in (week.get(i) or []):
            if a <= 765 < b and min(b, 840) - max(a, 720) >= 60:
                out.append(code)
                break
    return out


def days_de(codes):
    """['Mo','Tu','We','Th','Fr'] → „Mo–Fr“, ['Tu','Th','Sa'] → „Di, Do, Sa“, alle sieben → „täglich“."""
    idx = sorted({_OH_DAYS_EN.index(c) for c in (codes or []) if c in _OH_DAYS_EN})
    if len(idx) == 7:
        return 'täglich'
    runs, run = [], []
    for i in idx:
        if run and i != run[-1] + 1:
            runs.append(run); run = []
        run.append(i)
    if run:
        runs.append(run)
    parts = []
    for r in runs:
        de = [_OH_DAYS_DE[_OH_DAYS_EN[i]] for i in r]
        parts.append(f'{de[0]}–{de[-1]}' if len(de) >= 3 else ', '.join(de))
    return ', '.join(parts)


def _lunch_status(flag, text, days):
    """Gemeinsame Bewertung für eigene Einträge und OSM-Treffer → (status, label, kurz).
    status: 'yes' Mittagstisch bestätigt · 'no' ausdrücklich keiner · 'noon' laut Öffnungszeiten mittags
    geöffnet · 'noon_closed' laut Öffnungszeiten mittags zu · None keine Angaben."""
    flag = (flag or '').strip().lower()
    text = (text or '').strip()
    if flag == 'yes':
        return 'yes', '🍽️ Mittagstisch' + (f': {text}' if text else ''), 'Mittagstisch'
    if flag == 'no':
        return 'no', 'kein Mittagstisch' + (f' ({text})' if text else ''), 'kein Mittagstisch'
    if days:
        kurz = 'mittags geöffnet' + ('' if len(days) == 7 else ' ' + days_de(days))
        return 'noon', '🕛 ' + kurz, kurz
    if days is not None:
        return 'noon_closed', 'mittags geschlossen', 'mittags geschlossen'
    return None, '', ''


@app.template_global('lunch_info')
def lunch_info(spot):
    """Build z: Mittagstisch-Auskunft zu einem Gastro-Eintrag (Flag + Text aus dem Formular, sonst aus den
    Öffnungszeiten abgeleitet) → Dict(status, label, short, days (deutsche Kürzel), days_de, text, noon_known)."""
    hours = getattr(spot, 'hours_text', None) or ''
    if not hours and getattr(spot, 'opens_at', None) and getattr(spot, 'closes_at', None):
        hours = f'{spot.opens_at}-{spot.closes_at}'
    days = noon_days(hours)
    status, label, short = _lunch_status(getattr(spot, 'lunch', None), getattr(spot, 'lunch_text', None), days)
    return {'status': status, 'label': label, 'short': short,
            'days': [_OH_DAYS_DE[d] for d in (days or [])], 'days_de': days_de(days) if days else '',
            'text': (getattr(spot, 'lunch_text', None) or '').strip(), 'noon_known': days is not None}


def _lunch_from_tags(tags):
    """Build z: OSM-Tags lunch=yes|no|menu|buffet|<Zeiten>, lunch:menu/buffet/specials/tourist_menu=*
    → ('yes' | 'no' | None, Kurztext für die Anzeige)."""
    main = (tags.get('lunch') or '').strip()
    if main.lower() == 'no':
        return 'no', ''
    parts = []
    if main and main.lower() != 'yes':
        parts.append({'menu': 'Mittagsmenü', 'buffet': 'Buffet'}.get(main.lower()) or hours_de(main))
    for key, label in _LUNCH_SUB_DE.items():
        v = (tags.get('lunch:' + key) or '').strip()
        if v and v.lower() != 'no':
            parts.append(label + ('' if v.lower() == 'yes' else ' ' + hours_de(v)))
    if main or parts:
        return 'yes', ' · '.join(parts)[:200]
    return None, ''


def _cuisine_de(value):
    """OSM cuisine=german;regional → „deutsch, regional“."""
    out = []
    for v in re.split(r'[;,]', value or ''):
        v = v.strip().lower()
        if v:
            out.append(_CUISINE_DE.get(v, v.replace('_', ' ')))
    return ', '.join(dict.fromkeys(out))


def _lunch_enrich_result(r, tags):
    """OSM-Treffer um Mittagstisch-Felder ergänzen (Server und Browser-Fallback liefern dieselben Felder)."""
    r['lunch'], r['lunch_text'] = _lunch_from_tags(tags)
    r['kitchen_hours'] = tags.get('opening_hours:kitchen', '') or ''
    r['cuisine'] = _cuisine_de(tags.get('cuisine', ''))
    days = noon_days(r.get('opening_hours', ''), r['kitchen_hours'])
    r['noon_days'] = [_OH_DAYS_DE[d] for d in (days or [])]
    r['noon_known'] = days is not None
    r['lunch_status'], r['lunch_label'], _kurz = _lunch_status(r['lunch'], r['lunch_text'], days)
    return r


def open_now(hours_text, opens_at=None, closes_at=None, now=None):
    """Build aa: ('open' | 'closed' | None, 'HH:MM') – offen bis wann bzw. heute wieder ab wann;
    None, wenn keine Uhrzeiten lesbar sind. Zeitbasis Europe/Berlin."""
    hours = hours_text or ''
    if not hours and opens_at and closes_at:
        hours = f'{opens_at}-{closes_at}'
    week = _oh_week(hours)
    if not week or not any(week.values()):
        return None, ''
    if now is None:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo('Europe/Berlin'))
    wd, minute = now.weekday(), now.hour * 60 + now.minute

    def fmt(m):
        return f'{(m // 60) % 24:02d}:{m % 60:02d}'
    for a, b in (week.get((wd - 1) % 7) or []):          # gestern über Mitternacht hinaus geöffnet
        if b > 1440 and minute < b - 1440:
            return 'open', fmt(b - 1440)
    wins = week.get(wd)
    if wins is None:
        return None, ''
    for a, b in wins:
        if a <= minute < b:
            return 'open', ('' if (a, b) == (0, 1440) else fmt(b))   # „Di-So“ ohne Uhrzeit: offen, Ende unbekannt
    later = sorted(a for a, b in wins if a > minute)
    return 'closed', (fmt(later[0]) if later else '')


def _lunch_matches(status, noon_days_de, day=''):
    """Filter „Mittagstisch“: status yes/noon zählt; mit Wochentag (deutsches Kürzel) muss der Tag passen –
    ein bestätigter Mittagstisch ohne lesbare Zeiten gilt für jeden Tag."""
    if status == 'yes':
        return not day or not noon_days_de or day in noon_days_de
    if status == 'noon':
        return not day or day in noon_days_de
    return False


def _gastro_form_vals(spot=None, form=None):
    """Build t: Formularwerte – aus dem Eintrag (Bearbeiten) oder aus der fehlgeschlagenen Eingabe
    (vorher gingen bei einer Fehlermeldung alle eingegebenen Werte verloren)."""
    keys = ('name', 'spot_type', 'address', 'opens_at', 'closes_at', 'hours_text', 'phone', 'website',
            'notes', 'osm_id', 'lat', 'lng', 'lunch', 'lunch_text')   # Build z: Mittagstisch
    if form is not None:
        vals = {k: (form.get(k) or '') for k in keys}
    elif spot is not None:
        vals = {k: (getattr(spot, k, None) or '') for k in keys}
        vals['lat'] = f'{spot.lat:.6f}'
        vals['lng'] = f'{spot.lng:.6f}'
    else:
        vals = {k: '' for k in keys}
        vals['spot_type'] = 'cafe'
    return vals


def _gastro_match_known(cands, name, lat, lng, osm_id=None):
    """Build t/u: Passenden vorhandenen Eintrag aus cands finden – gleiche OSM-Verknüpfung, Punkt
    näher als 25 m oder gleicher Name im Umkreis von 100 m. Rückgabe (Eintrag, Grund) oder (None, None)."""
    if osm_id:
        for c in cands:
            if c.osm_id and c.osm_id == osm_id:
                return c, 'gleicher OpenStreetMap-Eintrag'
    if lat is None or lng is None:
        return None, None
    norm = re.sub(r'\W+', '', (name or '').lower())
    best = None
    for c in cands:
        dist = _geo_dist_m(lat, lng, c.lat, c.lng)
        if dist <= 25:
            return c, f'liegt nur {int(dist)} m entfernt'
        if norm and dist <= 100 and re.sub(r'\W+', '', (c.name or '').lower()) == norm:
            if best is None or dist < best[1]:
                best = (c, dist)
    if best:
        return best[0], f'gleicher Name, {int(best[1])} m entfernt'
    return None, None


def _gastro_find_duplicate(name, lat, lng, osm_id=None, exclude_id=None):
    """Build t: Gibt (Eintrag, Grund) zurück, wenn es den Ort schon gibt; sonst (None, None)."""
    q = GastroSpot.query
    if exclude_id:
        q = q.filter(GastroSpot.id != exclude_id)
    flt = []
    if osm_id:
        flt.append(GastroSpot.osm_id == osm_id)
    if lat is not None and lng is not None:
        flt.append(db.and_(GastroSpot.lat.between(lat - 0.002, lat + 0.002),
                           GastroSpot.lng.between(lng - 0.004, lng + 0.004)))
    if not flt:
        return None, None
    return _gastro_match_known(q.filter(db.or_(*flt)).all(), name, lat, lng, osm_id)


OSM_KIND_TO_TYPE = {'cafe': 'cafe', 'ice_cream': 'cafe', 'bar': 'kneipe', 'pub': 'kneipe', 'biergarten': 'kneipe',
                    'restaurant': 'restaurant', 'fast_food': 'imbiss', 'bakery': 'baeckerei', 'pastry': 'baeckerei'}
OSM_KIND_LABEL = {'cafe': 'Café', 'bar': 'Bar', 'pub': 'Kneipe', 'restaurant': 'Restaurant', 'biergarten': 'Biergarten',
                  'fast_food': 'Imbiss', 'bakery': 'Bäckerei', 'pastry': 'Konditorei', 'ice_cream': 'Eisdiele'}


def _simplify_track(points, max_pts=120):
    """Build u: Track auf höchstens max_pts Stützpunkte reduzieren (Douglas-Peucker, Toleranz wird
    verdoppelt, bis es passt) – für die Overpass-Polyline „around:r,lat1,lon1,lat2,lon2,…“."""
    import math
    pts = [(float(p['lat']), float(p['lng'])) for p in points if p.get('lat') is not None and p.get('lng') is not None]
    if len(pts) <= max_pts:
        return pts
    if len(pts) > 6000:                                   # Vorab ausdünnen, hält die Rechenzeit klein
        step = len(pts) // 6000 + 1
        pts = pts[::step] + [pts[-1]]
    mid = sum(p[0] for p in pts) / len(pts)
    m_lat, m_lng = 111320.0, 111320.0 * max(0.2, math.cos(math.radians(mid)))

    def rdp(seq, tol):
        keep = [False] * len(seq)
        keep[0] = keep[-1] = True
        stack = [(0, len(seq) - 1)]
        while stack:
            a, b = stack.pop()
            if b <= a + 1:
                continue
            ax, ay = seq[a][0] * m_lat, seq[a][1] * m_lng
            bx, by = seq[b][0] * m_lat, seq[b][1] * m_lng
            dx, dy = bx - ax, by - ay
            seg = dx * dx + dy * dy
            best_d, best_i = -1.0, a
            for i in range(a + 1, b):
                px, py = seq[i][0] * m_lat - ax, seq[i][1] * m_lng - ay
                t = max(0.0, min(1.0, (px * dx + py * dy) / seg)) if seg else 0.0
                d = math.hypot(px - t * dx, py - t * dy)
                if d > best_d:
                    best_d, best_i = d, i
            if best_d > tol:
                keep[best_i] = True
                stack.append((a, best_i))
                stack.append((best_i, b))
        return [p for p, k in zip(seq, keep) if k]

    tol = 15.0
    out = rdp(pts, tol)
    while len(out) > max_pts and tol < 5000:
        tol *= 2
        out = rdp(pts, tol)
    if len(out) > max_pts:                                # Notnagel: gleichmäßig ausdünnen
        step = len(out) // max_pts + 1
        out = out[::step] + [out[-1]]
    return out


def _along_track(points, items, max_m):
    """Build u: Für dicts mit lat/lng Abstand zum Track (dist_m), Streckenkilometer (km) und Anteil
    (frac) berechnen; nur Treffer ≤ max_m bleiben, sortiert nach km."""
    import math
    step = max(1, len(points) // 3000)
    pts = points[::step]
    if len(pts) < 2:
        return []
    mid = sum(p['lat'] for p in pts) / len(pts)
    m_lat, m_lng = 111320.0, 111320.0 * max(0.2, math.cos(math.radians(mid)))
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot((b['lat'] - a['lat']) * m_lat, (b['lng'] - a['lng']) * m_lng))
    out = []
    for it in items:
        best_d, best_i = 1e12, 0
        for i, pt in enumerate(pts):
            d = math.hypot((pt['lat'] - it['lat']) * m_lat, (pt['lng'] - it['lng']) * m_lng)
            if d < best_d:
                best_d, best_i = d, i
        if best_d <= max_m:
            it = dict(it)
            it.update({'dist_m': int(round(best_d)), 'km': round(cum[best_i] / 1000, 1),
                       'frac': best_i / max(1, len(pts) - 1)})
            out.append(it)
    out.sort(key=lambda x: (x['km'], x['dist_m']))
    return out


@app.route('/api/touren/<int:tour_id>/osm-gastro')
@login_required
def api_tour_osm_gastro(tour_id):
    """Build u: Gastronomie entlang der GPX-Strecke aus OpenStreetMap (Overpass-Polyline-Suche),
    mit Streckenkilometer, Abstand, Öffnungszeiten/Ruhetag und Hinweis, ob der Ort schon in der
    Gastro-Liste steht. Ergebnis je Tour/Radius 30 Minuten gecacht."""
    tour = _tour_or_404(tour_id)
    if not tour.gpx_file:
        return jsonify({'error': 'Diese Tour hat keine GPX-Strecke.'}), 400
    path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
    if not os.path.exists(path):
        return jsonify({'error': 'GPX-Datei nicht gefunden.'}), 404
    radius = max(50, min(1000, _parse_int(request.args.get('radius')) or 250))
    try:
        points = (parse_gpx(path) or {}).get('points') or []
    except Exception as e:
        return jsonify({'error': f'GPX nicht lesbar: {e}'}), 400
    if len(points) < 2:
        return jsonify({'error': 'Die GPX-Strecke enthält zu wenige Punkte.'}), 400
    simp = _simplify_track(points, 120)
    coords = ','.join(f'{la:.5f},{lo:.5f}' for la, lo in simp)
    ar = f'around:{radius},{coords}'
    query = (f'[out:json][timeout:25];\n(\n  node[{OVERPASS_AMENITY}]({ar});\n  way[{OVERPASS_AMENITY}]({ar});\n'
             f'  node[{OVERPASS_SHOP}]({ar});\n  way[{OVERPASS_SHOP}]({ar});\n);\nout center 120;\n')
    key = ('track', tour.id, int(os.path.getmtime(path)), radius)
    elements, source, error = _overpass_fetch(query, key, ttl=1800, budget_s=45)
    if elements is None:
        return jsonify({'error': f'Overpass nicht erreichbar: {error}', 'query': query}), 502
    results = _along_track(points, _overpass_elements_to_results(elements), radius + 30)
    # Schon vorhandene Einträge markieren – alle Kandidaten im Streckenkasten mit einer Abfrage holen
    known = []
    if results:
        lats = [r['lat'] for r in results]; lngs = [r['lng'] for r in results]
        osm_ids = [r['osm_id'] for r in results if r.get('osm_id')]
        known = GastroSpot.query.filter(db.or_(
            GastroSpot.osm_id.in_(osm_ids) if osm_ids else db.false(),
            db.and_(GastroSpot.lat.between(min(lats) - 0.002, max(lats) + 0.002),
                    GastroSpot.lng.between(min(lngs) - 0.004, max(lngs) + 0.004)))).all()
    for r in results:
        r['app_type'] = OSM_KIND_TO_TYPE.get(r['type'], 'other')
        r['type_label'] = OSM_KIND_LABEL.get(r['type'], r['type'] or 'Einkehr')
        r['hours'] = hours_de(r['opening_hours'])
        r['closed_days'] = closed_days(r['opening_hours'])
        dup, _reason = _gastro_match_known(known, r['name'], r['lat'], r['lng'], r['osm_id'])
        if dup:
            r['known_id'] = dup.id
            r['known_name'] = dup.name
            r['known_url'] = url_for('gastro_detail', spot_id=dup.id)
    return jsonify({'results': results, 'source': source, 'radius': radius, 'track_points': len(simp),
                    'cached': source == 'cache'})


@app.route('/api/gastro/quick-add', methods=['POST'])
@login_required
def api_gastro_quick_add():
    """Build u: OSM-Treffer (Streckensuche) mit einem Klick in die Gastro-Liste übernehmen.
    Existiert der Ort schon (osm_id / < 25 m / gleicher Name < 100 m), wird der vorhandene Eintrag
    zurückgegeben statt ein Duplikat anzulegen."""
    f = request.get_json(silent=True) or {}
    name = str(f.get('name') or '').strip()[:120]
    def _num(v):                                           # JSON liefert Zahlen, Formulare Strings
        try:
            return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else _parse_float(str(v or ''))
        except (TypeError, ValueError):
            return None
    lat, lng = _num(f.get('lat')), _num(f.get('lng'))
    if not name or lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({'error': 'Name und Koordinaten fehlen.'}), 400
    osm_id = str(f.get('osm_id') or '').strip()[:30] or None
    dup, reason = _gastro_find_duplicate(name, lat, lng, osm_id)
    if dup:
        return jsonify({'ok': True, 'existing': True, 'id': dup.id, 'name': dup.name, 'reason': reason,
                        'url': url_for('gastro_detail', spot_id=dup.id)})
    kind = str(f.get('type') or '')
    spot_type = OSM_KIND_TO_TYPE.get(kind) or (kind if kind in dict(GASTRO_TYPES) else 'other')
    hours = str(f.get('hours_text') or f.get('opening_hours') or '').strip()[:300] or None
    opens, closes = str(f.get('opens_at') or '').strip(), str(f.get('closes_at') or '').strip()
    if hours and not (opens and closes):
        m = re.search(r'(\d{2}:\d{2})-(\d{2}:\d{2})', hours)
        if m:
            opens, closes = opens or m.group(1), closes or m.group(2)
    spot = GastroSpot(
        name=name, spot_type=spot_type, lat=lat, lng=lng,
        address=str(f.get('address') or '').strip()[:200] or None,
        opens_at=opens if re.match(r'^\d{2}:\d{2}$', opens) else None,
        closes_at=closes if re.match(r'^\d{2}:\d{2}$', closes) else None,
        hours_text=hours,
        phone=str(f.get('phone') or '').strip()[:30] or None,
        website=_clean_url(str(f.get('website') or '')),
        notes=str(f.get('notes') or '').strip()[:500] or None,
        osm_id=osm_id, added_by=current_user.id,
    )
    lunch = str(f.get('lunch') or '').strip().lower()                                # Build z: Mittagstisch
    spot.lunch = lunch if lunch in ('yes', 'no') else None
    spot.lunch_text = str(f.get('lunch_text') or '').strip()[:200] or None
    db.session.add(spot)
    db.session.commit()
    return jsonify({'ok': True, 'existing': False, 'id': spot.id, 'name': spot.name,
                    'url': url_for('gastro_detail', spot_id=spot.id)})


def _gastro_can_edit(spot):
    """Build s: Eintrag ändern/löschen dürfen Admins, Organisatoren und wer ihn angelegt hat."""
    return bool(current_user.is_authenticated and
                (current_user.is_organizer or spot.added_by == current_user.id))


def _geo_dist_m(lat1, lng1, lat2, lng2):
    """Abstand zweier Koordinaten in Metern (äquirektangular – für wenige Kilometer völlig ausreichend)."""
    import math
    m_lng = 111320.0 * max(0.2, math.cos(math.radians((lat1 + lat2) / 2)))
    return math.hypot((lat1 - lat2) * 111320.0, (lng1 - lng2) * m_lng)


def _gastro_delete_photo_file(photo):
    try:
        path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photo.filename)
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        app.logger.warning(f'Gastro-Foto-Datei nicht gelöscht: {e}')


@app.route('/gastro/<int:spot_id>/fotos', methods=['POST'])
@login_required
def gastro_upload_photo(spot_id):
    """Foto zu Gastro-Spot hochladen (Build s: erstmals in der Detailseite eingebunden)."""
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
    caption = request.form.get('caption', '').strip()[:200] or None
    photo = GastroPhoto(spot_id=spot.id, user_id=current_user.id,
                        filename=filename, caption=caption)
    db.session.add(photo)
    db.session.commit()
    flash('Foto hochgeladen.', 'success')
    return redirect(url_for('gastro_detail', spot_id=spot_id) + '#fotos')


@app.route('/gastro/fotos/<int:photo_id>/loeschen', methods=['POST'])
@login_required
def gastro_delete_photo(photo_id):
    """Gastro-Foto löschen (eigenes Foto, Admin/Organisator oder Ersteller des Eintrags)."""
    photo = GastroPhoto.query.get_or_404(photo_id)
    if not (photo.user_id == current_user.id or _gastro_can_edit(photo.spot)):
        abort(403)
    _gastro_delete_photo_file(photo)
    spot_id = photo.spot_id
    db.session.delete(photo)
    db.session.commit()
    flash('Foto gelöscht.', 'success')
    return redirect(url_for('gastro_detail', spot_id=spot_id) + '#fotos')


@app.route('/gastro')
@login_required
def gastro_list():
    morning_only = request.args.get('morning') == '1'
    typ          = request.args.get('type', '')
    q            = request.args.get('q', '').strip()
    mittag       = request.args.get('mittag', '').strip()          # Build z: '' | '1' | 'Mo'…'So'
    if mittag not in ('', '1', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'):
        mittag = ''

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
        like = f'%{q}%'                                   # Build s: auch Adresse und Notizen durchsuchen
        spots = spots.filter(db.or_(GastroSpot.name.ilike(like), GastroSpot.address.ilike(like),
                                    GastroSpot.notes.ilike(like)))
    if typ:
        spots = spots.filter_by(spot_type=typ)
    if morning_only:
        spots = spots.filter(
            GastroSpot.opens_at != None,
            GastroSpot.opens_at <= morning_threshold
        )
    spots = spots.order_by(GastroSpot.name).all()
    lunch_by_id = {sp.id: lunch_info(sp) for sp in spots}            # Build z: Mittagstisch je Eintrag
    if mittag:
        spots = [sp for sp in spots
                 if _lunch_matches(lunch_by_id[sp.id]['status'], lunch_by_id[sp.id]['days'],
                                   '' if mittag == '1' else mittag)]

    # Build s: Bewertungsschnitt in EINER Abfrage statt je Karte neu (vorher 221 Abfragen bei 30
    # Einträgen); die Frühöffner-Schwelle liest das Model jetzt einmal je Request (models.morning_threshold)
    from sqlalchemy import func as _func
    avg_rows = (db.session.query(GastroReview.spot_id, _func.avg(GastroReview.score))
                .filter(GastroReview.score != None).group_by(GastroReview.spot_id).all())
    avgs = {sid: round(float(a), 1) for sid, a in avg_rows if a is not None}
    for sp in spots:
        sp._avg_rating = avgs.get(sp.id)
    # Build t: Kartendaten (Typ-Symbol, Öffnungszeiten, Ruhetage) und Treffpunkt für „nach Entfernung“
    spots_js = [{'id': sp.id, 'name': sp.name, 'spot_type': sp.spot_type, 'type': sp.type_label,
                 'lat': sp.lat, 'lng': sp.lng, 'opens': sp.opens_at or '', 'hours': hours_de(sp.hours_text),
                 'closed': closed_days(sp.hours_text), 'morning': bool(sp.is_morning_friendly),
                 'address': sp.address or '', 'rating': sp.avg_rating,
                 'lunch_status': lunch_by_id[sp.id]['status'], 'lunch_label': lunch_by_id[sp.id]['label'],
                 'lunch_text': lunch_by_id[sp.id]['text'], 'noon_days': lunch_by_id[sp.id]['days'],
                 'url': url_for('gastro_detail', spot_id=sp.id)} for sp in spots]
    meeting = None
    m_lat, m_lng = _parse_float(cfg('default_meeting_lat')), _parse_float(cfg('default_meeting_lng'))
    if m_lat is not None and m_lng is not None:
        meeting = {'lat': m_lat, 'lng': m_lng, 'desc': cfg('default_meeting_desc') or 'Treffpunkt'}
    return render_template('gastro/list.html', spots=spots, spots_js=spots_js, meeting=meeting,
                           gastro_types=GASTRO_TYPES, lunch_by_id=lunch_by_id, mittag=mittag,
                           morning_only=morning_only, typ=typ, q=q,
                           morning_threshold=morning_threshold)


def _gastro_fill_from_form(spot):
    """Build s: Formularfelder in einen Eintrag übernehmen (neu und bearbeiten identisch)."""
    spot.name      = request.form.get('name', '').strip()[:120]
    spot.spot_type = request.form.get('spot_type', 'cafe') or 'cafe'
    spot.address   = request.form.get('address', '').strip()[:200] or None
    spot.opens_at  = request.form.get('opens_at', '').strip()[:5] or None
    spot.closes_at = request.form.get('closes_at', '').strip()[:5] or None
    spot.hours_text = request.form.get('hours_text', '').strip()[:300] or None   # Build t
    lunch = request.form.get('lunch', '').strip().lower()                           # Build z: Mittagstisch
    spot.lunch      = lunch if lunch in ('yes', 'no') else None
    spot.lunch_text = request.form.get('lunch_text', '').strip()[:200] or None
    spot.phone     = request.form.get('phone', '').strip()[:30] or None
    spot.website   = _clean_url(request.form.get('website'))        # Audit 1.4.0: nur http(s)
    spot.notes     = request.form.get('notes', '').strip() or None
    osm_id = request.form.get('osm_id', '').strip()[:30]
    if osm_id:
        spot.osm_id = osm_id
    spot.lat = _parse_float(request.form.get('lat'))
    spot.lng = _parse_float(request.form.get('lng'))


@app.route('/gastro/neu', methods=['GET', 'POST'])
@login_required
def gastro_new():
    if request.method == 'POST':
        spot = GastroSpot(added_by=current_user.id)
        _gastro_fill_from_form(spot)
        # Audit 1.4.0: Name/Koordinaten prüfen statt 500 bei leeren Feldern
        if not spot.name or spot.lat is None or spot.lng is None:
            flash('Bitte Name angeben und einen Punkt auf der Karte wählen.', 'danger')
            return render_template('gastro/form.html', spot=None, gastro_types=GASTRO_TYPES,
                                   vals=_gastro_form_vals(form=request.form))
        # Build t: Doppelte Einträge vermeiden (gleiche osm_id, gleicher Name < 100 m, Punkt < 25 m)
        dup, reason = _gastro_find_duplicate(spot.name, spot.lat, spot.lng, spot.osm_id)
        if dup and not request.form.get('force'):
            from markupsafe import Markup, escape
            flash(Markup(f'„{escape(dup.name)}“ ist schon eingetragen ({escape(reason)}) – '
                         f'<a href="{url_for("gastro_detail", spot_id=dup.id)}" class="alert-link">zum Eintrag</a>. '
                         f'Ist es wirklich ein anderer Betrieb, unten „Trotzdem anlegen“ anhaken.'), 'warning')
            return render_template('gastro/form.html', spot=None, gastro_types=GASTRO_TYPES,
                                   vals=_gastro_form_vals(form=request.form), dup=dup)
        db.session.add(spot)
        db.session.commit()
        flash(f'"{spot.name}" wurde hinzugefügt!', 'success')
        return redirect(url_for('gastro_detail', spot_id=spot.id))
    return render_template('gastro/form.html', spot=None, gastro_types=GASTRO_TYPES, vals=_gastro_form_vals())


@app.route('/gastro/<int:spot_id>')
@login_required
def gastro_detail(spot_id):
    spot    = GastroSpot.query.get_or_404(spot_id)
    reviews = GastroReview.query.filter_by(spot_id=spot_id).order_by(GastroReview.created_at.desc()).all()
    my_rev  = GastroReview.query.filter_by(spot_id=spot_id, user_id=current_user.id).first()
    photos  = GastroPhoto.query.filter_by(spot_id=spot_id).order_by(GastroPhoto.created_at).all()
    return render_template('gastro/detail.html', spot=spot,
                           reviews=reviews, my_rev=my_rev,
                           photos=photos, can_edit=_gastro_can_edit(spot))


@app.route('/gastro/<int:spot_id>/bewerten', methods=['POST'])
@login_required
def gastro_review(spot_id):
    GastroSpot.query.get_or_404(spot_id)
    # Audit 1.4.0: Score nur 1–5, ungültige Werte ignorieren statt 500
    score = _parse_int(request.form.get('score'))
    if score is not None and not 1 <= score <= 5:
        score = None
    emoji = request.form.get('emoji','').strip()
    note  = request.form.get('note','').strip()

    existing = GastroReview.query.filter_by(spot_id=spot_id, user_id=current_user.id).first()
    if existing:
        existing.score = score
        existing.emoji = emoji or None
        existing.note  = note or None
    else:
        rev = GastroReview(
            spot_id = spot_id,
            user_id = current_user.id,
            score   = score,
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
    if not _gastro_can_edit(spot):
        abort(403)
    # Build s: Fotos (Dateien + Datensätze) mit entfernen – vorher IntegrityError/500, sobald ein Foto hing
    for photo in GastroPhoto.query.filter_by(spot_id=spot_id).all():
        _gastro_delete_photo_file(photo)
        db.session.delete(photo)
    db.session.delete(spot)
    db.session.commit()
    flash('Eintrag gelöscht.', 'success')
    return redirect(url_for('gastro_list'))


@app.route('/gastro/<int:spot_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def gastro_edit(spot_id):
    """Build s: Bearbeiten war unerreichbar (kein Link) und das Formular blieb leer – jetzt vorbelegt."""
    spot = GastroSpot.query.get_or_404(spot_id)
    if not _gastro_can_edit(spot):
        abort(403)
    if request.method == 'POST':
        _gastro_fill_from_form(spot)
        if spot.lat is None or spot.lng is None or not spot.name:
            db.session.rollback()
            flash('Ungültige Koordinaten.' if spot.name else 'Name ist erforderlich.', 'danger')
            return render_template('gastro/form.html', spot=GastroSpot.query.get(spot_id), gastro_types=GASTRO_TYPES,
                                   vals=_gastro_form_vals(form=request.form))
        db.session.commit()
        flash('Eintrag aktualisiert.', 'success')
        return redirect(url_for('gastro_detail', spot_id=spot.id))
    return render_template('gastro/form.html', spot=spot, gastro_types=GASTRO_TYPES, vals=_gastro_form_vals(spot=spot))


@app.route('/api/gastro/<int:spot_id>/osm-lookup')
@login_required
def gastro_osm_lookup(spot_id):
    """Build s: Ersatz für den Google-Places-Abgleich (brauchte einen kostenpflichtigen API-Key und war
    nie in der Oberfläche eingebunden). Sucht den Eintrag in OpenStreetMap – über die gespeicherte
    osm_id, sonst im Umkreis von 80 m – und liefert Kandidaten mit Öffnungszeiten, Adresse, Kontakt."""
    spot = GastroSpot.query.get_or_404(spot_id)
    m = re.match(r'^(node|way|relation)/(\d+)$', spot.osm_id or '')
    elements, source, error, query = None, None, None, None
    if m:
        query = f'[out:json][timeout:15];{m.group(1)}({m.group(2)});out center tags;'
        elements, source, error = _overpass_fetch(query, ('osm', spot.osm_id))
    if not elements:                                      # keine osm_id oder Objekt in OSM gelöscht
        query = _overpass_gastro_query_around(spot.lat, spot.lng, 80)
        elements, source, error = _overpass_fetch(query, ('near', round(spot.lat, 5), round(spot.lng, 5)))
    if elements is None:
        return jsonify({'error': f'Overpass nicht erreichbar: {error}', 'query': query}), 502
    results = _overpass_elements_to_results(elements)
    for r in results:
        r['distance_m'] = int(round(_geo_dist_m(spot.lat, spot.lng, r['lat'], r['lng'])))
    results.sort(key=lambda r: r['distance_m'])
    return jsonify({'results': results[:5], 'source': source})


@app.route('/gastro/<int:spot_id>/import', methods=['POST'])
@login_required
def gastro_import(spot_id):
    """Ausgewählte Felder aus dem OSM-Abgleich (JSON) in den Eintrag übernehmen."""
    spot = GastroSpot.query.get_or_404(spot_id)
    if not _gastro_can_edit(spot):
        abort(403)
    fields = request.get_json(silent=True) or {}   # Audit 1.4.0: kein 415 bei fehlendem Content-Type
    if fields.get('name'):      spot.name      = str(fields['name'])[:120]
    if fields.get('address'):   spot.address   = str(fields['address'])[:200]
    if fields.get('phone'):     spot.phone     = str(fields['phone'])[:30]
    if fields.get('website'):   spot.website   = _clean_url(str(fields['website']))
    if fields.get('osm_id'):    spot.osm_id    = str(fields['osm_id'])[:30]
    if fields.get('hours_text'): spot.hours_text = str(fields['hours_text'])[:300]   # Build t
    for key in ('opens_at', 'closes_at'):
        val = str(fields.get(key) or '').strip()
        if re.match(r'^\d{2}:\d{2}$', val):
            setattr(spot, key, val)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/touren/<int:tour_id>/videos', methods=['POST'])
@login_required
def tour_upload_video(tour_id):
    """MP4/Video-Datei zu einer Tour hochladen – direkt auf Disk streamen."""
    import traceback as _tb
    tour = _tour_or_404(tour_id)

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
                    # Audit 1.4.0: halbfertige Temp-Datei nicht liegen lassen
                    try:
                        os.remove(_faststart_path)
                    except Exception:
                        pass
        except Exception as _fe:
            # Audit 1.4.0: vorher NameError ('subprocess' fehlte) → Faststart lief nie
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
    tour  = _tour_or_404(video.tour_id)   # Audit 1.4.0: Gruppen-Check
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
        # Audit 1.4.0: Name/Koordinaten prüfen statt 500 bei leeren Feldern
        name = request.form.get('name', '').strip()
        lat  = _parse_float(request.form.get('lat'))
        lng  = _parse_float(request.form.get('lng'))
        if not name or lat is None or lng is None:
            flash('Bitte Name angeben und einen Punkt auf der Karte wählen.', 'danger')
            return render_template('orte/form.html', poi=None, poi_categories=POI_CATEGORIES)
        poi = POI(
            name        = name,
            category    = request.form.get('category','pausenort'),
            lat         = lat,
            lng         = lng,
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
    """Gruppen-Karte. Build aa: Popups mit Öffnungszeiten/Ruhetag/Mittagstisch/„jetzt geöffnet“ und Links,
    Filterdaten (Typ, Frühöffner, Mittagstisch, Suche), Treffpunkte mit Tour-Link, Startansicht auf dem
    Standard-Treffpunkt der Gruppe."""
    pois = POI.query.filter(
        (POI.is_shared == True) | (POI.added_by == current_user.id)
    ).order_by(POI.name).all()
    gastro = GastroSpot.query.order_by(GastroSpot.name).all()
    from sqlalchemy import func as _func                  # Bewertungsschnitt in einer Abfrage (wie gastro_list)
    avg_rows = (db.session.query(GastroReview.spot_id, _func.avg(GastroReview.score))
                .filter(GastroReview.score != None).group_by(GastroReview.spot_id).all())
    avgs = {sid: round(float(a), 1) for sid, a in avg_rows if a is not None}
    tours = (_gq(Tour).filter(Tour.meeting_lat != None, Tour.meeting_lng != None,
                              Tour.status != 'cancelled')
             .order_by(Tour.tour_date.desc()).limit(40).all())
    today = _berlin_today()

    pois_json = _json_for_script([{
        'id': p.id, 'name': p.name, 'cat': p.category,
        'icon': p.category_icon, 'label': p.category_label,
        'lat': p.lat, 'lng': p.lng, 'desc': p.description or '',
        'mine': p.added_by == current_user.id, 'url': url_for('poi_list', cat=p.category),
    } for p in pois])

    gastro_rows = []
    for g in gastro:
        g._avg_rating = avgs.get(g.id)
        li = lunch_info(g)
        state, until = open_now(g.hours_text, g.opens_at, g.closes_at)
        gastro_rows.append({
            'id': g.id, 'name': g.name, 'type': g.type_label, 'spot_type': g.spot_type,
            'lat': g.lat, 'lng': g.lng,
            'opens': g.opens_at or '', 'closes': g.closes_at or '',
            'hours': hours_de(g.hours_text), 'closed': closed_days(g.hours_text),
            'morning': bool(g.is_morning_friendly), 'rating': g.avg_rating,
            'notes': (g.notes or '')[:120], 'address': g.address or '',
            'lunch_status': li['status'], 'lunch_label': li['label'], 'lunch_text': li['text'],
            'noon_days': li['days'], 'open_now': state, 'open_until': until,
            'url': url_for('gastro_detail', spot_id=g.id),
            'text': f'{g.name} {g.address or ""} {g.notes or ""} {g.type_label} {li["short"]}'.lower(),
        })
    gastro_json = _json_for_script(gastro_rows)

    meetings_json = _json_for_script([{
        'id': t.id, 'title': t.title,
        'lat': t.meeting_lat, 'lng': t.meeting_lng,
        'desc': t.meeting_desc or '',
        'date': 'offen' if t.is_date_open else t.tour_date.strftime('%d.%m.%Y'),
        'time': t.start_time or '',
        'status': t.status,
        'upcoming': bool(t.status == 'planned' and (t.is_date_open or t.tour_date >= today)),
        'url': url_for('tour_detail', tour_id=t.id),
    } for t in tours])

    home = None
    h_lat, h_lng = _parse_float(cfg('default_meeting_lat')), _parse_float(cfg('default_meeting_lng'))
    if h_lat is not None and h_lng is not None:
        home = {'lat': h_lat, 'lng': h_lng, 'desc': cfg('default_meeting_desc') or 'Treffpunkt'}

    return render_template('karte.html',
                           pois_json=pois_json,
                           gastro_json=gastro_json,
                           meetings_json=meetings_json,
                           home_json=_json_for_script(home),
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

OVERPASS_ENDPOINTS = [            # Build r: Reihenfolge nach Verlässlichkeit (Stand 2026); kumi.systems ist oft nicht erreichbar
    'https://overpass-api.de/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]
_overpass_cache: dict = {}        # Cache-Schlüssel → (Zeitstempel, Overpass-Elemente); entlastet die Server, weniger Rate-Limits
OVERPASS_AMENITY = '"amenity"~"^(cafe|bar|pub|restaurant|fast_food|biergarten|ice_cream)$"'
OVERPASS_SHOP    = '"shop"~"^(bakery|pastry|ice_cream)$"'


def _osm_user_agent():
    """Build r: Eindeutiger User-Agent für OSM-Dienste. overpass-api.de lehnt seit April 2026 Anfragen
    ohne identifizierenden User-Agent mit „406 Not Acceptable“ ab (python-requests meldet sich nur
    als „python-requests/x.y“); Browser-Kennungen zu imitieren verbietet die Nutzungsordnung."""
    try:
        host = request.host_url.rstrip('/')
    except Exception:
        host = 'https://djo.wulmstorf.net'
    return f'DeJungenOlen/{APP_VERSION} (+{host}; Radgruppen-App, Gastro-Suche)'


def _overpass_gastro_query(s, w, n, e):
    """Overpass-QL für Gastronomie im Kartenausschnitt – Build r: zusätzlich Bäckereien/Konditoreien
    und Eisdielen (shop=bakery|pastry|ice_cream, amenity=ice_cream); „bakery“ war vorher fälschlich
    als amenity abgefragt und fand nie etwas."""
    bbox = f'{s},{w},{n},{e}'
    return (f'[out:json][timeout:15];\n(\n  node[{OVERPASS_AMENITY}]({bbox});\n  way[{OVERPASS_AMENITY}]({bbox});\n'
            f'  node[{OVERPASS_SHOP}]({bbox});\n  way[{OVERPASS_SHOP}]({bbox});\n);\nout center 80;\n')


def _overpass_gastro_query_around(lat, lng, radius_m, limit=20):
    """Build s: Gastronomie im Umkreis eines Punktes (für den OSM-Abgleich eines Eintrags)."""
    ar = f'around:{int(radius_m)},{lat:.6f},{lng:.6f}'
    return (f'[out:json][timeout:15];\n(\n  node[{OVERPASS_AMENITY}]({ar});\n  way[{OVERPASS_AMENITY}]({ar});\n'
            f'  node[{OVERPASS_SHOP}]({ar});\n  way[{OVERPASS_SHOP}]({ar});\n);\nout center {int(limit)};\n')


def _overpass_elements_to_results(elements):
    """Overpass-Elemente → kompakte Trefferliste (Name, Art, Position, Öffnungszeiten, Kontakt, Adresse).
    osm_id im OSM-Format „node/123“ (Build s), damit ein Eintrag später eindeutig wiedergefunden wird."""
    results = []
    for el in elements or []:
        tags = el.get('tags', {}) or {}
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lng = el.get('lon') or (el.get('center') or {}).get('lon')
        if not lat or not lng:
            continue
        kind = tags.get('amenity') or tags.get('shop') or ''
        street = ' '.join(x for x in (tags.get('addr:street'), tags.get('addr:housenumber')) if x)
        city = ' '.join(x for x in (tags.get('addr:postcode'), tags.get('addr:city')) if x)
        results.append(_lunch_enrich_result({
            'osm_id':  f"{el.get('type', 'node')}/{el.get('id', '')}",
            'name':    tags.get('name') or kind or 'Unbekannt',
            'type':    kind,
            'lat':     lat,
            'lng':     lng,
            'opening_hours': tags.get('opening_hours', ''),
            'phone':   tags.get('phone') or tags.get('contact:phone') or '',
            'website': tags.get('website') or tags.get('contact:website') or '',
            'address': ', '.join(x for x in (street, city) if x),
        }, tags))                                   # Build z: lunch/kitchen/cuisine + „mittags geöffnet“
    return results


def _overpass_fetch(query, cache_key=None, ttl=600, budget_s=40):
    """Build r/s: Overpass-Abfrage mit identifizierendem User-Agent, Ausweich-Servern (12 s je Server,
    Gesamtbudget budget_s, damit Passenger nicht abbricht) und kleinem In-Memory-Cache.
    Rückgabe (elements, quelle, fehler) – elements ist None, wenn kein Server geantwortet hat."""
    now = _time.time()
    if cache_key is not None:
        hit = _overpass_cache.get(cache_key)
        if hit and now - hit[0] < ttl:
            return hit[1], 'cache', None
    headers = {'User-Agent': _osm_user_agent(), 'Accept': 'application/json',
               'Referer': request.host_url if request else ''}
    status_hint = {406: 'Anfrage abgelehnt (406, User-Agent)', 429: 'zu viele Anfragen (429)',
                   504: 'Server überlastet (504)', 403: 'Zugriff verweigert (403)',
                   400: 'Abfrage abgelehnt (400)'}
    last_error = 'Unbekannter Fehler'
    deadline = now + budget_s
    for endpoint in OVERPASS_ENDPOINTS:
        if _time.time() > deadline:
            break
        host = endpoint.split('/')[2]
        try:
            resp = http_requests.post(endpoint, data={'data': query}, headers=headers, timeout=12)
            if resp.status_code != 200:
                last_error = f'{status_hint.get(resp.status_code, "HTTP " + str(resp.status_code))} bei {host}'
                app.logger.warning(f'Overpass {endpoint} -> {resp.status_code}: {(resp.text or "")[:200]!r}')
                if resp.status_code == 400:               # Syntaxfehler – andere Server antworten gleich
                    break
                continue
            try:
                data = resp.json()
            except ValueError:
                last_error = f'kein JSON von {host}'
                app.logger.error(f'Overpass JSON-Fehler ({endpoint}): {(resp.text or "")[:200]!r}')
                continue
            elements = data.get('elements') or []
            if cache_key is not None:
                if len(_overpass_cache) > 200:            # Cache klein halten
                    for old in sorted(_overpass_cache, key=lambda k: _overpass_cache[k][0])[:100]:
                        _overpass_cache.pop(old, None)
                _overpass_cache[cache_key] = (_time.time(), elements)
            return elements, host, None
        except http_requests.exceptions.Timeout:
            last_error = f'Zeitüberschreitung bei {host}'
            app.logger.warning(last_error)
        except Exception as ex:
            last_error = f'{host}: {ex.__class__.__name__}'
            app.logger.error(f'Overpass error ({endpoint}): {ex}')
    return None, None, last_error


@app.route('/api/overpass-gastro')
@login_required
def api_overpass_gastro():
    """Search OSM for amenities in a bounding box (Proxy für die Gastro-Suche „OSM-Gebiet“).
    Build r: identifizierender User-Agent (sonst 406), Ausweich-Server, Cache, sprechende Fehlertexte;
    bei Fehlern wird die Abfrage mitgeliefert, damit der Browser sie direkt an overpass-api.de stellen
    kann (eigene IP, eigener Referer – hilft, wenn die Hosting-IP im Rate-Limit steckt)."""
    try:
        s = float(request.args.get('s'))
        w = float(request.args.get('w'))
        n = float(request.args.get('n'))
        e = float(request.args.get('e'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Ungültiger Kartenausschnitt.'}), 400

    # Limit bbox size – at zoom 13+ the span stays well below 0.15°
    if (n - s) > 0.5 or (e - w) > 0.5:
        return jsonify({'error': 'Kartenausschnitt zu groß – bitte näher heranzoomen.', 'zoom_in': True}), 400

    query = _overpass_gastro_query(s, w, n, e)
    key = ('bbox', round(s, 3), round(w, 3), round(n, 3), round(e, 3))
    elements, source, error = _overpass_fetch(query, key)
    if elements is None:
        return jsonify({'error': f'Overpass nicht erreichbar: {error}', 'query': query}), 502
    return jsonify({'results': _overpass_elements_to_results(elements), 'source': source,
                    'cached': source == 'cache'})


# ─── Phase 2: Telegram reminder CLI ──────────────────────────────────────────

@app.cli.command('send-reminders')
def send_reminders():
    """Vorabend-Erinnerung (Telegram + Push) für die Touren von morgen – optional per
    Cron; seit Build ab verschickt der Selbst-Trigger dieselbe Nachricht automatisch."""
    tomorrow = _berlin_today() + timedelta(days=1)
    tours = Tour.query.filter_by(tour_date=tomorrow, status='planned').all()
    if not tours:
        print('Keine Touren morgen.')
        return
    for t in tours:
        attendees, push_sent = _send_evening_reminder_for_tour(t)
        print(f'Reminder gesendet: {t.title} ({push_sent}/{attendees} Push)')


# ─── Phase 3: Kommentare ─────────────────────────────────────────────────────

@app.route('/touren/<int:tour_id>/kommentieren', methods=['POST'])
@login_required
def tour_comment(tour_id):
    tour = _tour_or_404(tour_id)
    content   = request.form.get('content','').strip()
    # Audit 1.4.0: parent_id muss eine Zahl sein und zu einem Kommentar dieser Tour gehören
    parent_id = _parse_int(request.form.get('parent_id'))
    if parent_id is not None:
        parent = TourComment.query.get(parent_id)
        if not parent or parent.tour_id != tour_id:
            parent_id = None
    if not content:
        flash('Kommentar darf nicht leer sein.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour_id))

    comment = TourComment(
        tour_id   = tour_id,
        user_id   = current_user.id,
        content   = content,
        parent_id = parent_id
    )
    db.session.add(comment)
    db.session.commit()

    # Push-Benachrichtigung an alle zugesagten Teilnehmer (außer dem Kommentator selbst)
    try:
        attendee_ids = {p.user_id for p in
                        TourParticipant.query.filter_by(tour_id=tour_id, status='attending').all()}
        attendee_ids.discard(current_user.id)
        preview = content if len(content) <= 80 else content[:77] + '…'
        for uid in attendee_ids:
            u = User.query.get(uid)
            if u:
                send_push_to_user(
                    u, title=f'💬 {current_user.display_name} zu „{tour.title}"',
                    body=preview, url=f'/touren/{tour_id}#kommentare',
                )
    except Exception as e:
        app.logger.warning(f'Push notification (tour_comment) failed: {e}')

    # Telegram-Nachricht in die Gruppe
    try:
        tg_preview = content if len(content) <= 200 else content[:197] + '…'
        tg_msg = (
            f'💬 <b>Neuer Kommentar</b>\n\n'
            f'{_tg(current_user.display_name)} zu <b>{_tg(tour.title)}</b>:\n'
            f'"{_tg(tg_preview)}"\n\n'
            f'👉 {app.config["BASE_URL"]}/touren/{tour_id}#kommentare'
        )
        send_telegram(tg_msg)
    except Exception as e:
        app.logger.warning(f'Telegram notification (tour_comment) failed: {e}')

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

def badge_stats_bulk(user_ids):
    """Build ab: {user_id: (touren_mitgefahren, km_gesamt)} in EINER Abfrage statt
    je Nutzer eine – für Mitgliederliste, Rangliste und Rückblick."""
    if not user_ids:
        return {}
    rows = (db.session.query(TourParticipant.user_id,
                             db.func.count(TourParticipant.id),
                             db.func.coalesce(db.func.sum(Tour.gpx_km), 0.0))
            .join(Tour, Tour.id == TourParticipant.tour_id)
            .filter(TourParticipant.user_id.in_(list(user_ids)),
                    TourParticipant.confirmed_present == True)                # noqa: E712
            .group_by(TourParticipant.user_id).all())
    return {uid: (int(cnt or 0), float(km or 0.0)) for uid, cnt, km in rows}


def compute_badges(user, stats=None):
    """Return list of earned badge dicts for a user.
    Build ab: optional stats=(tour_count, total_km) aus badge_stats_bulk(), sonst eine
    Aggregat-Abfrage statt einer Abfrage pro Teilnahme."""
    if stats is None:
        stats = badge_stats_bulk([user.id]).get(user.id, (0, 0.0))
    tour_count, total_km = stats
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
    if (not current_user.is_admin and user.group_id and current_user.group_id
            and user.group_id != current_user.group_id):
        abort(404)
    stats  = user_stats(user)
    badges = compute_badges(user)

    from sqlalchemy.orm import contains_eager
    participations = (
        TourParticipant.query
        .filter_by(user_id=user_id, confirmed_present=True)
        .join(Tour)
        .options(contains_eager(TourParticipant.tour))     # Build ab: Tour gleich mitladen (kein N+1)
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
        ranking.append({'user': u, **s,
                        'badges': compute_badges(u, stats=(user_tours[uid], user_km[uid]))})   # Build ab: keine Extra-Abfragen

    ranking.sort(key=lambda r: (r['tour_count'], r['total_km']), reverse=True)
    annual = sorted(ranking, key=lambda r: r['tours_by_year'].get(year, 0), reverse=True)

    return render_template('rangliste.html', ranking=ranking, annual=annual,
                           year=year)


# ─── Build w: Fahrzeit/Streckenvorschau, Kalender-Abo, „Nochmal fahren“ ──────

def _track_preview(points, max_pts=60):
    """Mini-Streckenvorschau als kompakter String 'B,H|x,y x,y …' (längere Seite = 1000 Einheiten,
    y nach unten, Längengrad mit cos(Breite) gestaucht) – wird in der Archiv-Liste als Inline-SVG
    gezeichnet, ganz ohne Kachel-Anfragen. Leerer String, wenn der Track zu kurz ist."""
    import math
    pts = _simplify_track(points or [], max_pts=max_pts)
    if len(pts) < 2:
        return ''
    kx = math.cos(math.radians(sum(p[0] for p in pts) / len(pts)))
    xs = [p[1] * kx for p in pts]
    ys = [p[0] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny)
    if span <= 0:
        return ''
    scale = 1000.0 / span
    w = max(1, round((maxx - minx) * scale))
    h = max(1, round((maxy - miny) * scale))
    coords = ' '.join(f'{round((x - minx) * scale)},{round((maxy - y) * scale)}' for x, y in zip(xs, ys))
    return f'{w},{h}|{coords}'


def _tour_apply_gpx_metrics(tour, parsed):
    """Fahrzeit, Ø-Tempo (nur bei Zeitstempeln im GPX) und Streckenvorschau aus einem
    parse_gpx-Ergebnis übernehmen. gpx_preview != NULL gilt danach als „berechnet“."""
    tour.gpx_moving_s = int(parsed['moving_s']) if parsed.get('moving_s') else None
    tour.gpx_avg_kmh  = float(parsed['avg_kmh']) if parsed.get('avg_kmh') else None
    tour.gpx_preview  = _track_preview(parsed.get('points') or [])


@app.template_filter('hm')
def _hm_filter(seconds):
    """Sekunden → '2:35 h'."""
    m = int(round((seconds or 0) / 60))
    return f'{m // 60}:{m % 60:02d} h'


@app.template_filter('de1')
def _de1_filter(value):
    """Zahl mit einer Nachkommastelle und Komma ('16,8')."""
    try:
        return f'{float(value):.1f}'.replace('.', ',')
    except (TypeError, ValueError):
        return ''


@app.route('/admin/gpx-kennzahlen', methods=['POST'])
@login_required
@admin_required
def admin_gpx_metrics():
    """Fahrzeit/Ø-Tempo/Streckenvorschau für ältere Touren nachrechnen – zeitbegrenzt
    (≈20 s pro Klick), bei Bedarf mehrfach klicken."""
    import time as _time
    t0, done, failed = _time.time(), 0, 0
    pending = (Tour.query.filter(Tour.gpx_file != None, Tour.gpx_preview == None)
               .order_by(Tour.tour_date.desc()).limit(500).all())
    for t in pending:
        if _time.time() - t0 > 20:
            break
        path = _tour_gpx_path(t)
        parsed = parse_gpx(path) if path else None
        if parsed:
            _tour_apply_gpx_metrics(t, parsed)
            done += 1
        else:
            t.gpx_preview = ''           # Datei fehlt oder unlesbar – nicht wieder versuchen
            failed += 1
    db.session.commit()
    rest = Tour.query.filter(Tour.gpx_file != None, Tour.gpx_preview == None).count()
    msg = f'GPX-Kennzahlen: {done} Touren berechnet'
    if failed:
        msg += f', {failed} ohne lesbare GPX-Datei'
    msg += f' – noch {rest} offen, bitte erneut klicken.' if rest else ' – alle Touren sind aktuell.'
    flash(msg, 'info' if rest else 'success')
    return redirect(url_for('admin_tools'))


# Kalender-Abo (webcal): ein Token je Mitglied, Feed ohne Login, nur Touren der eigenen Gruppe

def _ics_escape(text):
    """Text für iCalendar maskieren (Backslash, Semikolon, Komma, Zeilenumbruch)."""
    return (str(text or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n'))


def _ics_fold(line):
    """RFC 5545: Zeilen auf höchstens 75 Oktette falten (Fortsetzungszeile beginnt mit Leerzeichen)."""
    out, cur, used = [], '', 0
    for ch in line:
        b = len(ch.encode('utf-8'))
        if used + b > 74:
            out.append(cur)
            cur, used = ' ' + ch, 1 + b
        else:
            cur += ch
            used += b
    out.append(cur)
    return '\r\n'.join(out)


def _ics_join(lines):
    return '\r\n'.join(_ics_fold(l) for l in lines) + '\r\n'


def _ics_event_lines(tour, stamp):
    """VEVENT-Zeilen einer Tour: stabile UID (Aktualisierungen ersetzen den Termin statt ihn zu
    doppeln), Start/Ende als lokale Zeit (4 h Dauer wie bisher), Absagen als STATUS:CANCELLED."""
    base = (app.config.get('BASE_URL') or request.url_root).rstrip('/')
    m = re.match(r'^\s*(\d{1,2})(?::(\d{2}))?', tour.start_time or '09:00')
    hh = min(int(m.group(1)), 23) if m else 9
    mm = min(int(m.group(2) or 0), 59) if m else 0
    d = tour.tour_date.strftime('%Y%m%d') if (tour.tour_date and not tour.is_date_open) else '20000101'
    desc = []
    if tour.status == 'cancelled':
        desc.append('ABGESAGT')
    if tour.difficulty:
        desc.append(f'Schwierigkeit: {tour.difficulty_label}')
    if tour.gpx_km:
        desc.append(f'Strecke: {tour.gpx_km} km' + (f', {int(tour.gpx_ascent)} Hm' if tour.gpx_ascent else ''))
    elif tour.approx_km:
        desc.append(f'Strecke: ca. {tour.approx_km:g} km')
    einkehr = _tour_einkehr_text(tour)
    if einkehr:
        desc.append(f'Einkehr: {einkehr}')
    if tour.description:
        desc.append(tour.description.strip())
    desc.append(f'Details: {base}/touren/{tour.id}')
    summary = ('Abgesagt: ' if tour.status == 'cancelled' else '🚴 ') + tour.title
    lines = ['BEGIN:VEVENT',
             f'UID:tour-{tour.id}@dejungenolen',
             f'DTSTAMP:{stamp}',
             f'DTSTART:{d}T{hh:02d}{mm:02d}00',
             f'DTEND:{d}T{min(hh + 4, 23):02d}{mm:02d}00',
             f'SUMMARY:{_ics_escape(summary)}',
             f'DESCRIPTION:{_ics_escape(chr(10).join(desc))}']
    if tour.meeting_desc:
        lines.append(f'LOCATION:{_ics_escape(tour.meeting_desc)}')
    if tour.meeting_lat and tour.meeting_lng:
        lines.append(f'GEO:{tour.meeting_lat:.6f};{tour.meeting_lng:.6f}')
    lines.append(f'URL:{base}/touren/{tour.id}')
    lines.append('STATUS:' + ('CANCELLED' if tour.status == 'cancelled' else 'CONFIRMED'))
    lines.append('END:VEVENT')
    return lines


def _tour_einkehr_text(tour):
    """Build x: geplante Einkehr als Kurztext (Erinnerung, ICS, tour.txt, Teilen) – '' wenn keine."""
    info = _einkehr_info(tour)
    if not info:
        return ''
    if info['spot']:
        parts = [info['name']]
        if info['type_label']:
            parts.append(info['type_label'])
        if info['hours']:
            parts.append(info['hours'])
        if info.get('lunch') == 'yes':                     # Build z
            parts.append(info['lunch_label'].replace('🍽️ ', '', 1))
        txt = ' · '.join(parts)
        if info['warn']:
            txt += ' – Achtung: am Tourtag Ruhetag?'
        elif info.get('noon_warn'):
            txt += ' – Achtung: am Tourtag mittags geschlossen?'
        if info['text']:
            txt += f' ({info["text"]})'
        return txt
    return info['text']


def _calendar_urls(user):
    """(https-URL, webcal-URL) des persönlichen Kalender-Feeds; Token wird beim ersten Aufruf erzeugt."""
    if not user.calendar_token:
        user.calendar_token = secrets.token_urlsafe(18)
        db.session.commit()
    https_url = url_for('calendar_feed', token=user.calendar_token, _external=True)
    return https_url, re.sub(r'^https?://', 'webcal://', https_url)


@app.route('/kalender/<token>.ics')
def calendar_feed(token):
    """Abonnierbarer Kalender (Token statt Login): Touren der eigenen Gruppe aus den letzten
    12 Monaten und alle kommenden; Änderungen und Absagen erscheinen beim nächsten Abgleich."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', token or ''):
        abort(404)
    user = User.query.filter_by(calendar_token=token).first()
    if not user or not user.is_active:
        abort(404)
    q = Tour.query.filter(Tour.tour_date != None, Tour.tour_date != date(9999, 12, 31),
                          Tour.tour_date >= date.today() - timedelta(days=365),
                          Tour.status.in_(('planned', 'completed', 'cancelled')))
    if user.group_id:
        q = q.filter(Tour.group_id == user.group_id)
    tours = q.order_by(Tour.tour_date).all()
    grp = Group.query.get(user.group_id) if user.group_id else None
    stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//De jungen Olen//Radgruppe//DE',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
             f'X-WR-CALNAME:{_ics_escape((grp.name if grp else "De jungen Olen") + " – Touren")}',
             'X-WR-TIMEZONE:Europe/Berlin',
             'REFRESH-INTERVAL;VALUE=DURATION:PT6H', 'X-PUBLISHED-TTL:PT6H']
    for t in tours:
        lines += _ics_event_lines(t, stamp)
    lines.append('END:VCALENDAR')
    resp = make_response(_ics_join(lines))
    resp.headers['Content-Type'] = 'text/calendar; charset=utf-8'
    resp.headers['Content-Disposition'] = 'inline; filename="touren.ics"'
    resp.headers['Cache-Control'] = 'private, max-age=300'
    return resp


@app.route('/profil/kalender/erneuern', methods=['POST'])
@login_required
def profil_calendar_renew():
    """Neuen Kalender-Link erzeugen – der alte Link funktioniert danach nicht mehr."""
    current_user.calendar_token = secrets.token_urlsafe(18)
    db.session.commit()
    flash('Neuer Kalender-Link erzeugt. Bitte das Abo auf dem Handy mit dem neuen Link neu einrichten.', 'success')
    return redirect(url_for('profil_edit') + '#kalender')


@app.route('/touren/<int:tour_id>/nochmal', methods=['POST'])
@login_required
@organizer_required
def tour_repeat(tour_id):
    """„Nochmal fahren“: Kopie einer (Archiv-)Tour als neue geplante Tour ohne Termin –
    Titel, Beschreibung, Startzeit, Level, Link, Treffpunkt und GPX-Track werden übernommen,
    Teilnehmer, Fotos und Fahrzeit nicht."""
    src = _tour_or_404(tour_id)
    new_gpx = None
    path = _tour_gpx_path(src)
    if path:
        import shutil
        new_gpx = f'tour_again_{secrets.token_hex(6)}.gpx'
        shutil.copy2(path, os.path.join(app.config['UPLOAD_FOLDER_GPX'], new_gpx))
    from flask import g as _g
    grp = getattr(_g, 'group', None)
    tour = Tour(
        title=src.title, description=src.description,
        tour_date=date(9999, 12, 31),            # Termin legt der Organisator gleich fest
        start_time=src.start_time, difficulty=src.difficulty, approx_km=src.approx_km,
        external_link=src.external_link, gpx_file=new_gpx,
        gpx_km=src.gpx_km if new_gpx else None, gpx_ascent=src.gpx_ascent if new_gpx else None,
        gpx_preview=(src.gpx_preview or None) if new_gpx else None,
        meeting_lat=src.meeting_lat, meeting_lng=src.meeting_lng, meeting_desc=src.meeting_desc,
        status='planned', created_by=current_user.id,
        group_id=src.group_id or (grp.id if grp else None),
    )
    for col in ('gastro_spot_id', 'einkehr_text'):          # Build x: geplante Einkehr mitnehmen
        if hasattr(Tour, col):
            setattr(tour, col, getattr(src, col))
    db.session.add(tour)
    db.session.commit()
    flash(f'„{src.title}“ wird nochmal gefahren – jetzt den Termin festlegen!', 'success')
    return redirect(url_for('tour_detail', tour_id=tour.id))


# ─── Build x: Großschrift, geplante Einkehr, Anwesenheit ───────────────────────────────────

GASTRO_TYPE_LABELS = {'cafe': 'Café', 'kneipe': 'Kneipe/Gasthaus', 'baeckerei': 'Bäckerei',
                      'restaurant': 'Restaurant', 'imbiss': 'Imbiss', 'other': 'Einkehr'}


def _einkehr_info(tour, today=None):
    """Geplante Einkehr einer Tour als Dict für Templates/Texte oder None.
    Felder: spot (GastroSpot|None), name, type_label, hours, closed_days, warn (Tourtag = Ruhetag),
    url, lat, lng, address, text (Freitext)."""
    spot = None
    if getattr(tour, 'gastro_spot_id', None):
        spot = db.session.get(GastroSpot, tour.gastro_spot_id)
    text = (getattr(tour, 'einkehr_text', None) or '').strip()
    if not spot and not text:
        return None
    if not spot:
        return {'spot': None, 'name': text, 'type_label': '', 'hours': '', 'closed_days': [],
                'warn': False, 'url': '', 'lat': None, 'lng': None, 'address': '', 'text': text,
                'lunch': None, 'lunch_label': '', 'noon_warn': False}
    cdays = closed_days(getattr(spot, 'hours_text', None)) or []
    lunch = lunch_info(spot)                                   # Build z: Mittagstisch / mittags geöffnet
    warn = noon_warn = False
    try:
        if tour.tour_date and not tour.is_date_open:
            wd = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][tour.tour_date.weekday()]
            warn = any(d.startswith(wd) for d in cdays)
            noon_warn = bool(lunch['noon_known'] and lunch['status'] not in ('yes', 'no')
                             and wd not in lunch['days'])
    except Exception:
        warn = noon_warn = False
    hours = hours_de(getattr(spot, 'hours_text', None)) or ''
    if not hours and spot.opens_at:
        hours = f'ab {spot.opens_at} Uhr'
    return {'spot': spot, 'name': spot.name,
            'type_label': GASTRO_TYPE_LABELS.get(spot.spot_type, 'Einkehr'),
            'hours': hours, 'closed_days': cdays, 'warn': warn,
            'url': url_for('gastro_detail', spot_id=spot.id),
            'lat': spot.lat, 'lng': spot.lng, 'address': spot.address or '', 'text': text,
            'lunch': lunch['status'], 'lunch_label': lunch['label'], 'noon_warn': noon_warn}


def gastro_spot_choices():
    """Auswahlliste für die Tour-Formulare (alle Gastro-Einträge, alphabetisch)."""
    try:
        return [(sp.id, sp.name, GASTRO_TYPE_LABELS.get(sp.spot_type, 'Einkehr'))
                for sp in GastroSpot.query.order_by(GastroSpot.name).all()]
    except Exception:
        return []


app.jinja_env.globals['einkehr_info'] = _einkehr_info
app.jinja_env.globals['gastro_spot_choices'] = gastro_spot_choices


def _apply_einkehr_form(tour):
    """Formularfelder gastro_spot_id / einkehr_text (Tour anlegen/bearbeiten) auf die Tour schreiben."""
    raw = (request.form.get('gastro_spot_id') or '').strip()
    spot_id = int(raw) if raw.isdigit() else None
    if spot_id and not db.session.get(GastroSpot, spot_id):
        spot_id = None
    tour.gastro_spot_id = spot_id
    tour.einkehr_text = (request.form.get('einkehr_text') or '').strip()[:200] or None


def _planned_einkehr_entry(tour, points):
    """Video (Build j-Folie): geplante Einkehr als erste Zeile – mit km/Abstand, wenn ein Track da ist."""
    info = _einkehr_info(tour)
    if not info or not info['spot']:
        return None
    sp = info['spot']
    entry = {'id': sp.id, 'name': sp.name, 'spot_type': sp.spot_type, 'type_label': info['type_label'],
             'lat': sp.lat, 'lng': sp.lng, 'dist_m': 0, 'km': 0.0, 'frac': 0.0,
             'opens_at': sp.opens_at or '', 'hours': info['hours'], 'closed_days': info['closed_days'],
             'lunch_status': info.get('lunch'), 'lunch_label': info.get('lunch_label', ''),
             'planned': True, 'km_known': False}
    try:
        import math as _m
        pts = [pt for pt in points if pt.get('lat') is not None and pt.get('lng') is not None]
        if len(pts) >= 2:
            m_lat = 111_320.0
            m_lng = 111_320.0 * _m.cos(_m.radians(pts[0]['lat']))
            cum, best_d, best_i = [0.0], 1e12, 0
            for a, b in zip(pts, pts[1:]):
                cum.append(cum[-1] + _m.hypot((b['lat'] - a['lat']) * m_lat, (b['lng'] - a['lng']) * m_lng))
            for i, pt in enumerate(pts):
                d = _m.hypot((pt['lat'] - sp.lat) * m_lat, (pt['lng'] - sp.lng) * m_lng)
                if d < best_d:
                    best_d, best_i = d, i
            entry.update({'dist_m': int(round(best_d)), 'km': round(cum[best_i] / 1000, 1),
                          'frac': best_i / max(1, len(pts) - 1), 'km_known': True})
    except Exception:
        pass
    return entry


def _can_manage_tour(tour):
    return current_user.is_admin or current_user.is_organizer or tour.created_by == current_user.id


@app.route('/touren/<int:tour_id>/einkehr', methods=['POST'])
@login_required
def tour_set_einkehr(tour_id):
    """Geplante Einkehr setzen/entfernen – aus der Gastro-Ebene, der OSM-Streckensuche (JSON) oder
    dem ✕ in der Tour-Kopfzeile (Formular). spot_id leer/0 = entfernen."""
    tour = _tour_or_404(tour_id)
    if not _can_manage_tour(tour):
        abort(403)
    data = request.get_json(silent=True) or {}
    raw = data.get('spot_id') if data else request.form.get('spot_id')
    raw = str(raw if raw is not None else '').strip()
    spot = db.session.get(GastroSpot, int(raw)) if raw.isdigit() and int(raw) > 0 else None
    tour.gastro_spot_id = spot.id if spot else None
    if 'einkehr_text' in (data or request.form):
        tour.einkehr_text = str((data or request.form).get('einkehr_text') or '').strip()[:200] or None
    elif not spot:
        tour.einkehr_text = None
    db.session.commit()
    txt = _tour_einkehr_text(tour)
    if data or request.is_json:
        return jsonify({'ok': True, 'spot_id': tour.gastro_spot_id, 'text': txt})
    flash(f'Einkehr: {txt}' if txt else 'Einkehr entfernt.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour.id))


@app.route('/profil/grossschrift', methods=['POST'])
@login_required
def profil_large_text():
    """Großschrift-Modus ein-/ausschalten (pro Nutzer gespeichert) – aus dem Konto-Menü."""
    current_user.large_text = not bool(getattr(current_user, 'large_text', False))
    db.session.commit()
    flash('Große Schrift eingeschaltet.' if current_user.large_text else 'Normale Schrift eingeschaltet.', 'info')
    from urllib.parse import urlsplit
    ref = urlsplit(request.referrer or '')
    if ref.netloc == request.host and ref.path and not ref.path.startswith('/profil/grossschrift'):
        return redirect(ref.path + (f'?{ref.query}' if ref.query else ''))   # nur eigener Host, nur Pfad
    return redirect(url_for('my_profil'))


def _self_confirm_window(tour, today=None):
    """Darf ein Teilnehmer „Ich war dabei“ drücken? Nur am Tourtag und bis 3 Tage danach."""
    today = today or date.today()
    if not tour.tour_date or tour.is_date_open or tour.status not in ('planned', 'completed'):
        return False
    return tour.tour_date <= today <= tour.tour_date + timedelta(days=3)


@app.route('/touren/<int:tour_id>/ich-war-dabei', methods=['POST'])
@login_required
def tour_self_confirm(tour_id):
    """Selbstbestätigung der Teilnahme (zählt für die Rangliste) – am Tourtag und bis 3 Tage danach."""
    tour = _tour_or_404(tour_id)
    if not _self_confirm_window(tour):
        flash('Die Teilnahme kann nur am Tourtag und bis drei Tage danach bestätigt werden.', 'warning')
        return redirect(url_for('tour_detail', tour_id=tour.id))
    p = TourParticipant.query.filter_by(tour_id=tour.id, user_id=current_user.id).first()
    if not p:
        p = TourParticipant(tour_id=tour.id, user_id=current_user.id, status='attending')
        db.session.add(p)
    p.status = 'attending'
    p.confirmed_present = True
    db.session.commit()
    flash('Danke – deine Teilnahme ist bestätigt.', 'success')
    return redirect(url_for('tour_detail', tour_id=tour.id) + '#teilnehmer')


def _attendance_recipients(tour):
    """Ersteller + aktive Organisatoren/Admins der Tour-Gruppe (ohne Dubletten)."""
    seen, out = set(), []
    q = User.query.filter(User.is_active == True, User.role.in_(['organizer', 'admin']))  # noqa: E712
    if tour.group_id:
        q = q.filter(User.group_id == tour.group_id)
    cands = ([tour.creator] if tour.creator else []) + q.all()
    for u in cands:
        if u and u.id not in seen:
            seen.add(u.id)
            out.append(u)
    return out


def _attendance_open(tour):
    return not any(p.confirmed_present for p in tour.participants)


def _send_attendance_reminder_for_tour(tour):
    """Abend-Push „Wer war dabei?“ an Ersteller/Organisatoren; ohne Push-Abo E-Mail an den Ersteller."""
    n_att = sum(1 for p in tour.participants if p.status == 'attending')
    body = f'„{tour.title}“ ({tour.tour_date.strftime("%d.%m.")}): {n_att} angemeldet – bitte Anwesenheit abhaken, damit die Rangliste stimmt.'
    url = f'/touren/{tour.id}#anwesenheit'
    sent = 0
    for u in _attendance_recipients(tour):
        try:
            n, _ = send_push_to_user(u, title='✅ Wer war dabei?', body=body, url=url)
            sent += n
        except Exception as e:
            app.logger.warning(f'attendance push failed for user {u.id}: {e}')
    if not sent and tour.creator and tour.creator.email:
        try:
            send_mail(tour.creator.email, f'Wer war dabei? – {tour.title}',
                      f'Moin {tour.creator.display_name},\n\n{body}\n\n'
                      f'{app.config["BASE_URL"]}{url}\n\nDe jungen Olen')
        except Exception as e:
            app.logger.warning(f'attendance mail failed: {e}')
    tour.attendance_reminded_at = datetime.utcnow()
    return sent


def _run_attendance_reminders(force=False):
    """Fällige Touren (Tourtag bis 3 Tage zurück, nichts bestätigt, noch nicht erinnert) anstoßen.
    Ohne force nur abends ab 17 Uhr (Europe/Berlin). Liefert die Zahl der erinnerten Touren."""
    today = date.today()
    if not force:
        try:
            from zoneinfo import ZoneInfo
            hour = datetime.now(ZoneInfo('Europe/Berlin')).hour
        except Exception:
            hour = datetime.now().hour
        if hour < 17:
            return 0
    due = Tour.query.filter(Tour.status.in_(['planned', 'completed']),
                            Tour.tour_date <= today,
                            Tour.tour_date >= today - timedelta(days=3),
                            Tour.attendance_reminded_at == None).all()   # noqa: E711
    done = 0
    for tour in due:
        if _attendance_open(tour):
            _send_attendance_reminder_for_tour(tour)
            done += 1
        else:
            tour.attendance_reminded_at = datetime.utcnow()   # schon abgehakt → nicht mehr erinnern
    if due:
        db.session.commit()
    return done


@app.before_request
def _self_trigger_attendance_reminder():
    """Wie die Morgen-Erinnerung: ohne Cron, ~3 % der Requests prüfen abends, ob eine Tour offen ist."""
    if request.endpoint in ('static', 'service_worker', 'api_backup_trigger'):
        return
    import random
    if random.random() > 0.03:
        return
    try:
        flag_key = f'attendance_reminder_run_{date.today().isoformat()}'
        if cfg(flag_key) == '1':
            return
        if _run_attendance_reminders() >= 0:
            try:
                from zoneinfo import ZoneInfo
                hour = datetime.now(ZoneInfo('Europe/Berlin')).hour
            except Exception:
                hour = datetime.now().hour
            if hour >= 17:                      # Tagesflag erst setzen, wenn der Abendlauf wirklich stattfand
                _set_day_flag('attendance_reminder_run_', flag_key)   # Build ab: alte Tagesflags mit löschen
                db.session.commit()
    except Exception as e:
        app.logger.warning(f'Self-trigger attendance reminder error: {e}')


def _attendance_todo(group_id, today=None, days=14):
    """Für Organisatoren: Touren der letzten `days` Tage ohne eine einzige bestätigte Teilnahme."""
    today = today or date.today()
    q = Tour.query.filter(Tour.status.in_(['planned', 'completed']),
                          Tour.tour_date <= today,
                          Tour.tour_date >= today - timedelta(days=days))
    if group_id:
        q = q.filter(Tour.group_id == group_id)
    return [t for t in q.order_by(Tour.tour_date.desc()).all() if _attendance_open(t)]


@app.route('/admin/anwesenheit-erinnern', methods=['POST'])
@login_required
@admin_required
def admin_attendance_reminders():
    """Admin → Werkzeuge: Abend-Erinnerung sofort prüfen/verschicken (ohne Uhrzeit-Sperre)."""
    try:
        n = _run_attendance_reminders(force=True)
        flash(f'Anwesenheits-Erinnerung: {n} Tour(en) angestoßen.' if n else
              'Anwesenheits-Erinnerung: keine offene Tour der letzten 3 Tage.', 'success' if n else 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler: {e}', 'danger')
    return redirect(url_for('admin_tools'))


# ─── Build v: Downloads – GPX-Einzeldatei, GPX-ZIP nach Auswahl, Tour-Paket ──

def _safe_filename_part(text, maxlen=40):
    """Titel → Dateinamen-tauglicher Teil (Umlaute bleiben, alles andere wird zu _)."""
    part = re.sub(r'[^A-Za-z0-9äöüÄÖÜß_-]+', '_', (text or '').strip()).strip('_')
    return part[:maxlen].rstrip('_') or 'Tour'


def _tour_file_stem(tour):
    """'2025-06-14_Deichtour' – Datumsteil 'offen', wenn kein echtes Datum gesetzt ist."""
    d = tour.tour_date.strftime('%Y-%m-%d') if (tour.tour_date and not tour.is_date_open) else 'offen'
    return f'{d}_{_safe_filename_part(tour.title)}'


def _tour_gpx_path(tour):
    """Absoluter Pfad der GPX-Datei – None, wenn keine gesetzt oder die Datei fehlt."""
    if not tour.gpx_file:
        return None
    path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], os.path.basename(tour.gpx_file))
    return path if os.path.isfile(path) else None


def _archiv_filter_query(q='', year='', diff=''):
    """Auswahl der Archiv-Suche (abgeschlossene Touren der Gruppe), auch für den GPX-ZIP-Download."""
    tours = _gq(Tour).filter(Tour.status == 'completed')
    if q:
        tours = tours.filter(Tour.title.ilike(f'%{q}%'))
    if year and str(year).isdigit():
        tours = tours.filter(db.extract('year', Tour.tour_date) == int(year))
    if diff in ('leicht', 'mittel', 'schwer'):
        tours = tours.filter(Tour.difficulty == diff)
    return tours


def _archiv_years():
    """Jahre mit abgeschlossenen Touren (neueste zuerst), ohne den Platzhalter 9999."""
    rows = (_gq(Tour).with_entities(db.extract('year', Tour.tour_date))
            .filter(Tour.status == 'completed', Tour.tour_date != None,
                    Tour.tour_date != date(9999, 12, 31))
            .distinct().order_by(db.extract('year', Tour.tour_date).desc()).all())
    return [int(r[0]) for r in rows if r[0] is not None]


def _zip_response(fill, download_name):
    """ZIP in einer Temp-Datei aufbauen (nicht im RAM) und als Download ausliefern.
    fill(zf) schreibt die Einträge; die Temp-Datei verschwindet nach dem Senden."""
    import tempfile, zipfile
    tmp = tempfile.TemporaryFile()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
        fill(zf)
    tmp.seek(0)
    return send_file(tmp, mimetype='application/zip', as_attachment=True,
                     download_name=download_name, max_age=0)


def _gpx_zip(tours, download_name):
    """GPX-Dateien mehrerer Touren als ZIP ('2025-06-14_Titel.gpx', bei Namensgleichheit _2, _3 …)."""
    used = set()

    def fill(zf):
        for t in tours:
            src = _tour_gpx_path(t)
            if not src:
                continue
            stem, name, n = _tour_file_stem(t), None, 1
            while True:
                name = f'{stem}.gpx' if n == 1 else f'{stem}_{n}.gpx'
                if name not in used:
                    break
                n += 1
            used.add(name)
            zf.write(src, name)
    return _zip_response(fill, download_name)


@app.route('/touren/<int:tour_id>/gpx-datei')
@login_required
def tour_gpx_download(tour_id):
    """GPX einer Tour – nur mit Login und nur für die eigene Gruppe, mit sprechendem Dateinamen."""
    tour = _tour_or_404(tour_id)
    if not _tour_gpx_path(tour):
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER_GPX'], os.path.basename(tour.gpx_file),
                               as_attachment=True, download_name=_tour_file_stem(tour) + '.gpx',
                               mimetype='application/gpx+xml', max_age=0)


@app.route('/archiv/gpx-zip')
@login_required
def archiv_gpx_zip():
    """GPX-Tracks der aktuellen Archiv-Auswahl (Suchbegriff/Jahr/Level – oder alle Jahre) als ZIP."""
    q    = request.args.get('q', '').strip()
    year = request.args.get('year', '').strip()
    diff = request.args.get('diff', '').strip()
    tours = (_archiv_filter_query(q, year, diff).filter(Tour.gpx_file != None)
             .order_by(Tour.tour_date.asc()).all())
    tours = [t for t in tours if _tour_gpx_path(t)]
    if not tours:
        flash('In dieser Auswahl gibt es keine GPX-Tracks.', 'warning')
        if q or year or diff:
            return redirect(url_for('archiv_suche', q=q, year=year, diff=diff))
        return redirect(url_for('archiv'))
    label = year if year.isdigit() else 'alle_Jahre'
    if q:
        label += '_' + _safe_filename_part(q, 20)
    if diff:
        label += '_' + diff
    return _gpx_zip(tours, f'dejungen_olen_gpx_{label}.zip')


def _tour_package_text(tour, participants, photos, photo_names, videos, gpx_name):
    """Inhalt der tour.txt im Tour-Paket (reiner Text, UTF-8)."""
    L = []
    grp = Group.query.get(tour.group_id) if tour.group_id else None
    head = f'{grp.name if grp else "De jungen Olen"} – Tour-Paket'
    L += [head, '=' * len(head), '']
    if tour.tour_date and not tour.is_date_open:
        d = tour.tour_date
        datum = f'{_DE_WEEKDAYS[d.weekday()][:2]}, {d.strftime("%d.%m.%Y")}'
        if tour.start_time:
            datum += f' · {tour.start_time} Uhr'
    else:
        datum = 'offen'
    status = {'planned': 'geplant', 'completed': 'abgeschlossen', 'cancelled': 'abgesagt'}.get(tour.status, tour.status)
    if tour.gpx_km:
        strecke = f'{tour.gpx_km:.1f} km'.replace('.', ',')
        if tour.gpx_ascent:
            strecke += f' · {int(tour.gpx_ascent)} Hm'
        strecke += ' (aus GPX)'
    elif tour.approx_km:
        strecke = f'ca. {tour.approx_km:g} km'.replace('.', ',')
    else:
        strecke = '–'
    treff = tour.meeting_desc or ''
    if tour.meeting_lat and tour.meeting_lng:
        treff += f' ({tour.meeting_lat:.5f}, {tour.meeting_lng:.5f})'
    rows = [('Titel', tour.title), ('Datum', datum), ('Status', status),
            ('Schwierigkeit', tour.difficulty_label), ('Strecke', strecke),
            ('Treffpunkt', treff.strip() or '–'), ('Einkehr', _tour_einkehr_text(tour)),   # Build x
            ('Link', tour.external_link or ''),
            ('Organisiert von', tour.creator.display_name if tour.creator else ''),
            ('Tour-Seite', url_for('tour_detail', tour_id=tour.id, _external=True))]
    try:
        w = json.loads(tour.weather_json or '{}').get('data') or {}
        if w.get('label'):
            rows.insert(5, ('Wetter', f'{w.get("icon", "")} {w.get("label")}, '
                                      f'{w.get("temp_min", "?")}–{w.get("temp_max", "?")} °C'.strip()))
    except (ValueError, AttributeError):
        pass
    for k, v in rows:
        if v:
            L.append(f'{k + ":":<17}{v}')
    if tour.description:
        L += ['', 'Beschreibung', '-' * 12, tour.description.strip()]
    confirmed = [p for p in participants if p.confirmed_present]
    listed    = confirmed or [p for p in participants if p.status == 'attending']
    title     = (f'Teilnehmer ({len(listed)}, bestätigt)' if confirmed
                 else f'Angemeldet ({len(listed)})')
    L += ['', title, '-' * len(title)]
    L += [f'- {p.user.display_name}' for p in listed] or ['–']
    title = f'Fotos ({len(photos)})'
    L += ['', title, '-' * len(title)]
    for p, name in zip(photos, photo_names):
        bits = [name]
        if p.caption:
            bits.append(f'„{p.caption}“')
        bits.append(f'von {p.user.display_name}')
        if p.taken_at:
            bits.append(p.taken_at.strftime('%d.%m.%Y %H:%M'))
        if p.lat and p.lng:
            bits.append(f'{p.lat:.5f}, {p.lng:.5f}')
        L.append(' – '.join(bits))
    if not photos:
        L.append('–')
    if videos:
        title = f'Videos ({len(videos)}) – nicht im Paket (zu groß), Download auf der Tour-Seite'
        L += ['', title, '-' * len(title)]
        L += [f'- {v.title or v.filename}' + (f' ({v.filesize / 1048576:.1f} MB)' if v.filesize else '')
              for v in videos]
    L += ['', 'Dateien', '-' * 7]
    L.append(f'{gpx_name} – GPX-Track' if gpx_name else '(kein GPX-Track vorhanden)')
    if photos:
        L.append(f'fotos/ – {len(photos)} Fotos (max. 1600 px, Reihenfolge wie auf der Tour-Seite)')
    L += ['', f'Erstellt am {datetime.now().strftime("%d.%m.%Y %H:%M")} von {current_user.display_name} '
              f'– De jungen Olen {APP_VERSION}']
    return '\r\n'.join(L) + '\r\n'


@app.route('/touren/<int:tour_id>/paket')
@login_required
def tour_package(tour_id):
    """Tour-Paket: GPX-Track, alle Fotos und tour.txt als ZIP (Videos bleiben wegen der Größe draußen)."""
    tour   = _tour_or_404(tour_id)
    stem   = _tour_file_stem(tour)
    gpx    = _tour_gpx_path(tour)
    photos = tour.photos.order_by(db.text('COALESCE(sort_order, 999999) ASC'),
                                  TourPhoto.taken_at.asc().nullslast(),
                                  TourPhoto.created_at.asc()).all()
    videos = TourVideo.query.filter_by(tour_id=tour.id).order_by(TourVideo.created_at).all()
    participants = (TourParticipant.query.filter_by(tour_id=tour.id)
                    .join(User, TourParticipant.user_id == User.id).order_by(User.name).all())
    folder = os.path.realpath(app.config['UPLOAD_FOLDER_PHOTOS'])
    files, names = [], []
    for i, p in enumerate(photos, 1):
        src = os.path.realpath(os.path.join(folder, p.filename or ''))
        if not (src.startswith(folder + os.sep) and os.path.isfile(src)):
            continue
        ext  = os.path.splitext(src)[1].lower() or '.jpg'
        name = f'{i:02d}' + (f'_{_safe_filename_part(p.caption, 30)}' if p.caption else '') + ext
        files.append((p, src, name))
        names.append(name)
    photos_ok = [f[0] for f in files]
    gpx_name  = f'{stem}.gpx' if gpx else None
    text      = _tour_package_text(tour, participants, photos_ok, names, videos, gpx_name)

    def fill(zf):
        import zipfile
        zf.writestr('tour.txt', text.encode('utf-8'))
        if gpx:
            zf.write(gpx, gpx_name)
        for _p, src, name in files:                      # JPEGs: nicht erneut komprimieren
            zf.write(src, f'fotos/{name}', compress_type=zipfile.ZIP_STORED)
    return _zip_response(fill, f'{stem}_Tour-Paket.zip')


# Apache soll die privaten Upload-Ordner nie direkt ausliefern. Greift nur, falls der Hoster
# /static über Apache bedient (bei Passenger läuft ohnehin alles über die App, siehe
# _protect_private_uploads). Fotos/Videos/GPX gehen ausschließlich über serve_photo,
# serve_video und tour_gpx_download, daher ist das Verbot gefahrlos.
_UPLOAD_HTACCESS = (
    '# De jungen Olen – von der App angelegt (Build v).\n'
    '# Fotos, Videos und GPX-Dateien werden nur über die App (mit Login) ausgeliefert.\n'
    '<IfModule mod_authz_core.c>\n    Require all denied\n</IfModule>\n'
    '<IfModule !mod_authz_core.c>\n    Order deny,allow\n    Deny from all\n</IfModule>\n')


def _ensure_upload_htaccess():
    """Legt in den privaten Upload-Ordnern einmalig eine .htaccess an (fehlertolerant)."""
    for key in ('UPLOAD_FOLDER_GPX', 'UPLOAD_FOLDER_PHOTOS', 'UPLOAD_FOLDER_VIDEOS'):
        folder = app.config.get(key)
        if not folder:
            continue
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, '.htaccess')
            if not os.path.exists(path):
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(_UPLOAD_HTACCESS)
        except OSError as ex:
            app.logger.warning(f'.htaccess in {folder} nicht anlegbar: {ex}')


# ─── Phase 3: Jahresrückblick ─────────────────────────────────────────────────

@app.route('/touren/gpx-export')
@login_required
def gpx_export_all():
    """Alle GPX-Tracks eines Jahres als ZIP herunterladen (Jahresrückblick)."""
    year  = request.args.get('year', date.today().year, type=int)
    tours = _gq(Tour).filter(
        db.extract('year', Tour.tour_date) == year,
        Tour.gpx_file != None,
        Tour.status == 'completed'
    ).order_by(Tour.tour_date).all()
    tours = [t for t in tours if _tour_gpx_path(t)]
    if not tours:
        flash(f'Keine GPX-Tracks für {year} gefunden.', 'warning')
        return redirect(url_for('rueckblick', year=year))
    return _gpx_zip(tours, f'dejungen_olen_gpx_{year}.zip')    # Build v: Temp-Datei statt RAM


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


@app.route('/api/backup/trigger', methods=['GET', 'POST'])
def api_backup_trigger():
    """Externer Trigger-Endpunkt für automatische Backups.
    Für Plesk 'Geplante Aufgaben' (curl/wget) gedacht, ODER wird zusätzlich
    bei jedem normalen Seitenaufruf geprüft (Selbst-Trigger als Fallback).
    Geschützt durch Token statt Login, da Cronjobs sich nicht einloggen können.
    """
    token = request.args.get('token', '')
    expected = (app.config.get('SECRET_KEY') or '')[:20]
    import hmac as _hmac
    if (not expected or expected.startswith('change-me')
            or not _hmac.compare_digest(token.encode(), expected.encode())):
        return jsonify({'error': 'invalid token'}), 403

    due = _backup_is_due()
    if not due:
        return jsonify({'ok': True, 'skipped': True, 'reason': 'not due yet'})

    ok, msg = _run_backup(triggered_by='cron', mode=due)
    return jsonify({'ok': ok, 'mode': due, 'message': msg})


@app.route('/admin/backup/einstellungen', methods=['POST'])
@login_required
@admin_required
def admin_backup_settings():
    """Backup-Intervall und Benachrichtigungs-Einstellung speichern."""
    interval = request.form.get('backup_interval', 'off')
    if interval not in ('off', 'daily', 'weekly', 'monthly'):
        interval = 'off'
    SiteConfig.set('backup_interval', interval)
    SiteConfig.set('backup_notify_email', '1' if request.form.get('backup_notify_email') == '1' else '0')
    SiteConfig.set('backup_include_videos', '1' if request.form.get('backup_include_videos') == '1' else '0')  # Build ab
    db.session.commit()
    labels = {'off': 'deaktiviert', 'daily': 'täglich', 'weekly': 'wöchentlich', 'monthly': 'monatlich'}
    flash(f'Automatisches Komplett-Backup: {labels[interval]}'
          + (' – Datenbank zusätzlich täglich.' if interval != 'off' else '.'), 'success')
    return redirect(url_for('admin_backups_list'))


@app.route('/admin/backup/cron-info')
@login_required
@admin_required
def admin_backup_cron_info():
    """Zeigt die fertige URL zum Eintragen in Plesk 'Geplante Aufgaben'."""
    token = (app.config.get('SECRET_KEY') or '')[:20]
    trigger_url = url_for('api_backup_trigger', token=token, _external=True)
    return render_template('admin/backup_cron_info.html', trigger_url=trigger_url)


@app.route('/admin/backup/aufraeumen', methods=['POST'])
@login_required
@admin_required
def admin_backup_rotate_now():
    """Manuell alte Backups sofort nach Generationen-Prinzip aufräumen."""
    try:
        deleted = _rotate_backups()
        if deleted:
            flash(f'{deleted} alte(s) Backup(s) gelöscht.', 'success')
        else:
            flash('Nichts zu löschen – alle Backups sind noch innerhalb der Aufbewahrungsfrist.', 'info')
    except Exception as e:
        flash(f'Fehler beim Aufräumen: {e}', 'danger')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/reminder-test', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_reminder_test():
    """Alte URL – leitet zur neuen, zusammengeführten Benachrichtigungs-Testseite."""
    if request.method == 'POST':
        tour_id = request.form.get('tour_id')
        tour = _tour_or_404(tour_id)
        if request.form.get('kind') == 'evening':                      # Build ab
            attendees, push_sent = _send_evening_reminder_for_tour(tour)
            flash(f'Vorabend-Erinnerung für „{tour.title}" verschickt: Telegram-Nachricht gesendet, '
                  f'{push_sent} von {attendees} Teilnehmer(n) (Dabei/Vielleicht) per Push benachrichtigt.',
                  'success')
            return redirect(url_for('admin_notifications'))
        attendees, push_sent = _send_morning_reminder_for_tour(tour)
        flash(f'Test-Erinnerung für „{tour.title}" verschickt: '
              f'Telegram-Nachricht gesendet, {push_sent} von {attendees} '
              f'zugesagten Teilnehmer(n) per Push benachrichtigt.', 'success')
        return redirect(url_for('admin_notifications'))
    return redirect(url_for('admin_notifications'))


@app.route('/admin/benachrichtigungen/erinnerungen', methods=['POST'])
@login_required
@admin_required
def admin_reminder_settings():
    """Build ab: Uhrzeiten der automatischen Erinnerungen (Tourtag / Vorabend)."""
    def _hour(name, default):
        try:
            h = int(request.form.get(name, default))
        except (TypeError, ValueError):
            h = default
        return str(min(23, max(0, h)))
    SiteConfig.set('reminder_morning_hour', _hour('reminder_morning_hour', 7))
    SiteConfig.set('reminder_evening_hour', _hour('reminder_evening_hour', 18))
    SiteConfig.set('reminder_evening_enabled', '1' if request.form.get('reminder_evening_enabled') else '0')
    db.session.commit()
    flash('Erinnerungs-Zeiten gespeichert.', 'success')
    return redirect(url_for('admin_notifications'))


def get_visible_announcements(group_id=None, context='logged_in'):
    """Gibt aktuell sichtbare Ankündigungen zurück.
    Mit group_id: nur die dieser Gruppe (für eingeloggte Nutzer).
    Ohne group_id (None): ALLE aktiven Ankündigungen gruppenübergreifend –
    für den ausgeloggten Login-Screen, wo noch kein Gruppen-Kontext besteht.
    context: 'logged_in' oder 'logged_out' – filtert nach der je Ankündigung
    einstellbaren Sichtbarkeit (visibility: 'both'/'logged_in'/'logged_out')."""
    q = Announcement.query.filter_by(is_active=True)
    if group_id is not None:
        q = q.filter_by(group_id=group_id)
    q = q.filter(db.or_(Announcement.visibility == 'both', Announcement.visibility == context))
    now = datetime.utcnow()
    q = q.filter(
        db.or_(Announcement.starts_at == None, Announcement.starts_at <= now),
        db.or_(Announcement.expires_at == None, Announcement.expires_at >= now),
    )
    return q.order_by(Announcement.created_at.desc()).all()


@app.route('/admin/ankuendigungen')
@login_required
@admin_required
def admin_announcements():
    """Übersicht aller Ankündigungen der aktiven Gruppe."""
    from flask import g as _g_ann
    grp = getattr(_g_ann, 'group', None)
    items = Announcement.query.filter_by(group_id=grp.id if grp else None) \
                              .order_by(Announcement.created_at.desc()).all()
    return render_template('admin/announcements.html', items=items)


@app.route('/admin/ankuendigungen/neu', methods=['POST'])
@login_required
@admin_required
def announcement_create():
    """Erstellt eine neue Ankündigung, optional mit Bild."""
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    if not title:
        flash('Titel ist erforderlich.', 'danger')
        return redirect(url_for('admin_announcements'))

    from flask import g as _g_ann
    grp = getattr(_g_ann, 'group', None)

    image_fname = None
    image_file = request.files.get('image')
    if image_file and image_file.filename:
        ext = image_file.filename.rsplit('.', 1)[-1].lower()
        if ext in ('jpg', 'jpeg', 'png', 'webp'):
            ann_dir = os.path.join(app.root_path, 'static', 'uploads', 'announcements')
            os.makedirs(ann_dir, exist_ok=True)
            image_fname = f'ann_{secrets.token_hex(8)}.{ext}'
            image_path = os.path.join(ann_dir, image_fname)
            image_file.save(image_path)
            try:
                _resize_photo_if_needed(image_path, max_px=1400)
            except Exception:
                pass
        else:
            flash('Bild: nur JPG, PNG oder WEBP erlaubt – Ankündigung wurde ohne Bild erstellt.', 'warning')

    starts_at = None
    expires_at = None
    if request.form.get('starts_at'):
        try:
            starts_at = datetime.strptime(request.form['starts_at'], '%Y-%m-%d')
        except ValueError:
            pass
    if request.form.get('expires_at'):
        try:
            expires_at = datetime.strptime(request.form['expires_at'], '%Y-%m-%d') + timedelta(hours=23, minutes=59)
        except ValueError:
            pass

    visibility = request.form.get('visibility', 'both')
    if visibility not in ('both', 'logged_in', 'logged_out'):
        visibility = 'both'

    ann = Announcement(
        group_id=grp.id if grp else None,
        title=title, content=content or None, image=image_fname,
        visibility=visibility,
        starts_at=starts_at, expires_at=expires_at,
        created_by=current_user.id,
    )
    db.session.add(ann)
    db.session.commit()
    flash(f'Ankündigung „{title}" erstellt.', 'success')
    return redirect(url_for('admin_announcements'))


@app.route('/admin/ankuendigungen/<int:ann_id>/bearbeiten', methods=['POST'])
@login_required
@admin_required
def announcement_edit(ann_id):
    """Bearbeitet eine bestehende Ankündigung. Bild bleibt erhalten, falls
    kein neues hochgeladen wird; kann über die Checkbox entfernt werden."""
    ann = Announcement.query.get_or_404(ann_id)

    title = request.form.get('title', '').strip()
    if not title:
        flash('Titel ist erforderlich.', 'danger')
        return redirect(url_for('admin_announcements'))

    ann.title = title
    ann.content = request.form.get('content', '').strip() or None

    ann_dir = os.path.join(app.root_path, 'static', 'uploads', 'announcements')

    if request.form.get('remove_image') == '1' and ann.image:
        old_path = os.path.join(ann_dir, ann.image)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        ann.image = None

    image_file = request.files.get('image')
    if image_file and image_file.filename:
        ext = image_file.filename.rsplit('.', 1)[-1].lower()
        if ext in ('jpg', 'jpeg', 'png', 'webp'):
            os.makedirs(ann_dir, exist_ok=True)
            if ann.image:
                old_path = os.path.join(ann_dir, ann.image)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass
            new_fname = f'ann_{secrets.token_hex(8)}.{ext}'
            image_path = os.path.join(ann_dir, new_fname)
            image_file.save(image_path)
            try:
                _resize_photo_if_needed(image_path, max_px=1400)
            except Exception:
                pass
            ann.image = new_fname
        else:
            flash('Bild: nur JPG, PNG oder WEBP erlaubt – restliche Änderungen wurden trotzdem gespeichert.', 'warning')

    visibility = request.form.get('visibility', 'both')
    if visibility not in ('both', 'logged_in', 'logged_out'):
        visibility = 'both'
    ann.visibility = visibility

    ann.starts_at = None
    ann.expires_at = None
    if request.form.get('starts_at'):
        try:
            ann.starts_at = datetime.strptime(request.form['starts_at'], '%Y-%m-%d')
        except ValueError:
            pass
    if request.form.get('expires_at'):
        try:
            ann.expires_at = datetime.strptime(request.form['expires_at'], '%Y-%m-%d') + timedelta(hours=23, minutes=59)
        except ValueError:
            pass

    db.session.commit()
    flash(f'Ankündigung „{title}" aktualisiert.', 'success')
    return redirect(url_for('admin_announcements'))


@app.route('/admin/ankuendigungen/<int:ann_id>/loeschen', methods=['POST'])
@login_required
@admin_required
def announcement_delete(ann_id):
    """Löscht eine Ankündigung inkl. Bild."""
    ann = Announcement.query.get_or_404(ann_id)
    if ann.image:
        img_path = os.path.join(app.root_path, 'static', 'uploads', 'announcements', ann.image)
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except OSError:
                pass
    title = ann.title
    db.session.delete(ann)
    db.session.commit()
    flash(f'Ankündigung „{title}" gelöscht.', 'success')
    return redirect(url_for('admin_announcements'))


@app.route('/admin/ankuendigungen/<int:ann_id>/umschalten', methods=['POST'])
@login_required
@admin_required
def announcement_toggle(ann_id):
    """Aktiviert/deaktiviert eine Ankündigung, ohne sie zu löschen."""
    ann = Announcement.query.get_or_404(ann_id)
    ann.is_active = not ann.is_active
    db.session.commit()
    flash(f'Ankündigung „{ann.title}" {"aktiviert" if ann.is_active else "deaktiviert"}.', 'success')
    return redirect(url_for('admin_announcements'))


@app.route('/admin/tools')
@login_required
@admin_required
def admin_tools():
    """Zentrale Übersicht aller Admin-Werkzeuge (Backup, Benachrichtigungen,
    Gruppen, Diagnose, Pakete) – Sammelstelle statt verstreuter Einzellinks."""
    backup_count = 0
    backups_dir = os.path.join(os.path.dirname(__file__), 'backups')
    if os.path.isdir(backups_dir):
        backup_count = len([f for f in os.listdir(backups_dir)
                            if f.startswith('djo_backup_') and f.endswith('.tar.gz')])
    group_count = Group.query.filter_by(is_active=True).count()
    _last_run_str = cfg('backup_last_run')
    _last_run = None
    if _last_run_str:
        try:
            _last_run = datetime.fromisoformat(_last_run_str)
        except ValueError:
            pass
    return render_template('admin/tools.html',
                           backup_count=backup_count,
                           group_count=group_count,
                           backup_last_run=_last_run,
                           backup_last_status=cfg('backup_last_status'))


@app.route('/admin/benachrichtigungen')
@login_required
@admin_required
def admin_notifications():
    """Zentrale Test- und Statusseite für alle Benachrichtigungswege:
    Push, Telegram und die Tourtag-Erinnerung."""
    telegram_configured = bool(cfg('telegram_bot_token') and cfg('telegram_chat_id'))
    push_available = False
    try:
        from py_vapid import Vapid02  # noqa
        import pywebpush  # noqa
        push_available = True
    except Exception:
        push_available = False
    from flask import g as _g_notif
    _grp = getattr(_g_notif, 'group', None)
    push_sub_count = PushSubscription.query.join(User).filter(
        User.group_id == (_grp.id if _grp else None)
    ).count() if push_available else 0

    upcoming = (_gq(Tour)
                .filter(Tour.status == 'planned', Tour.tour_date >= date.today())
                .order_by(Tour.tour_date.asc())
                .limit(10).all())

    return render_template('admin/notifications.html',
                           telegram_configured=telegram_configured,
                           push_available=push_available,
                           push_sub_count=push_sub_count,
                           tours=upcoming,
                           reminder_morning_hour=_cfg_int('reminder_morning_hour', 7, 0, 23),     # Build ab
                           reminder_evening_hour=_cfg_int('reminder_evening_hour', 18, 0, 23),
                           reminder_evening_enabled=(cfg('reminder_evening_enabled') != '0'))


def _resolve_live_db_path():
    """Ermittelt den tatsächlichen Dateipfad der aktiven SQLite-Datenbank
    aus der SQLALCHEMY_DATABASE_URI-Konfiguration.

    WICHTIG: Flask-SQLAlchemy löst relative sqlite:///-Pfade standardmäßig
    relativ zu app.instance_path auf (üblicherweise <projekt>/instance/),
    NICHT relativ zum Projekt-Hauptordner! Das war zuvor nicht berücksichtigt."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
    candidates = []

    if uri.startswith('sqlite:///'):
        db_path = uri[len('sqlite:///'):]
        db_path = db_path.split('?')[0]  # eventuelle Query-Parameter abschneiden
        if not os.path.isabs(db_path):
            db_path = os.path.join(app.instance_path, db_path)
        candidates.append(db_path)

    # Fallback-Kandidaten: instance-Ordner zuerst (Flask-Standard), dann Projektroot
    app_dir = os.path.dirname(__file__)
    candidates.append(os.path.join(app.instance_path, 'dejungen_olen.db'))
    candidates.append(os.path.join(app_dir, 'instance', 'dejungen_olen.db'))
    candidates.append(os.path.join(app_dir, 'dejungen_olen.db'))
    candidates.append(os.path.join(app_dir, 'djo.sqlite'))

    for c in candidates:
        if c and os.path.exists(c):
            return c

    return candidates[0] if candidates else None


@app.route('/admin/db-diagnose')
@login_required
@admin_required
def admin_db_diagnose():
    """Zeigt, welche Datenbank-Konfiguration aktiv ist und welche
    .db/.sqlite-Dateien tatsächlich im Projektordner UND im
    Flask-instance-Ordner liegen (dorthin werden relative sqlite:///-Pfade
    von Flask-SQLAlchemy standardmäßig aufgelöst)."""
    app_dir = os.path.dirname(__file__)
    instance_dir = app.instance_path
    configured_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '(nicht gesetzt)')

    found_files = []
    search_dirs = [('Projektordner', app_dir), ('instance-Ordner', instance_dir)]
    seen_paths = set()
    for label, directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for fname in os.listdir(directory):
            if fname.endswith(('.db', '.sqlite', '.sqlite3')):
                fpath = os.path.join(directory, fname)
                if fpath in seen_paths:
                    continue
                seen_paths.add(fpath)
                try:
                    found_files.append({
                        'name': fname,
                        'location': label,
                        'full_path': fpath,
                        'size_mb': round(os.path.getsize(fpath) / (1024*1024), 2),
                        'mtime': datetime.fromtimestamp(os.path.getmtime(fpath)),
                    })
                except OSError:
                    continue
    found_files.sort(key=lambda x: x['mtime'], reverse=True)

    # Zusätzlich: was SQLAlchemy selbst als aktive Engine-URL führt
    try:
        engine_url = str(db.engine.url)
    except Exception as e:
        engine_url = f'(Fehler beim Lesen: {e})'

    return render_template('admin/db_diagnose.html',
                           app_dir=app_dir,
                           instance_dir=instance_dir,
                           configured_uri=configured_uri,
                           engine_url=engine_url,
                           found_files=found_files)


@app.route('/push/vapid-public-key')
@login_required
def push_vapid_public_key():
    """Liefert den öffentlichen VAPID-Schlüssel für die Browser-Subscription."""
    _, pub = _get_vapid_keys()
    if not pub:
        return jsonify({'error': 'Push-Benachrichtigungen sind serverseitig nicht verfügbar '
                                  '(pywebpush/cryptography nicht installiert). '
                                  'Admin → Pakete installieren.'}), 503
    return jsonify({'publicKey': pub})


@app.route('/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    """Speichert eine neue Browser-Push-Subscription für den aktuellen Nutzer."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Unvollständige Subscription-Daten'}), 400

    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.user_id = current_user.id
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.session.add(PushSubscription(
            user_id=current_user.id, endpoint=endpoint, p256dh=p256dh, auth=auth
        ))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    """Entfernt eine Push-Subscription (z.B. wenn der Nutzer Benachrichtigungen abschaltet)."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user.id).delete()
        db.session.commit()
    return jsonify({'ok': True})


@app.route('/push/test', methods=['POST'])
@login_required
def push_test():
    """Sendet eine Test-Benachrichtigung an den aktuellen Nutzer."""
    sent, reasons = send_push_to_user(current_user, 'Testbenachrichtigung 🔔',
                                      'Push-Benachrichtigungen funktionieren!', url='/')
    if sent:
        return jsonify({'ok': True, 'sent': sent})
    detail = '; '.join(reasons) if reasons else 'Unbekannter Fehler'
    return jsonify({'ok': False, 'error': f'Versand fehlgeschlagen: {detail}'}), 400


@app.route('/admin/backups')
@login_required
@admin_required
def admin_backups_list():
    """Übersicht aller verfügbaren Backups zum Wiederherstellen."""
    backups_dir = os.path.join(os.path.dirname(__file__), 'backups')
    entries = []
    if os.path.isdir(backups_dir):
        for fname in sorted(os.listdir(backups_dir), reverse=True):
            if not fname.endswith('.tar.gz') or not (fname.startswith('djo_backup_') or fname.startswith('djo_db_')):
                continue
            fpath = os.path.join(backups_dir, fname)
            try:
                size_mb = round(os.path.getsize(fpath) / (1024*1024), 1)
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                entries.append({'filename': fname, 'size_mb': size_mb, 'mtime': mtime,
                                'kind': 'db' if fname.startswith('djo_db_') else 'full'})   # Build ab
            except OSError:
                continue
    entries.sort(key=lambda e: e['mtime'], reverse=True)
    return render_template('admin/backups_list.html', backups=entries,
                           backup_interval=cfg('backup_interval') or 'off',
                           backup_notify_email=cfg('backup_notify_email') or '0',
                           backup_include_videos=cfg('backup_include_videos') or '0',
                           backup_running=_backup_lock.locked())


@app.route('/admin/backups/<path:filename>/wiederherstellen', methods=['POST'])
@login_required
@admin_required
def admin_backup_restore(filename):
    """Stellt ein Backup wieder her: Datenbank + Uploads (fehlende Dateien ergänzt).
    Erstellt vorher automatisch eine Sicherheitskopie der aktuellen Datenbank.
    ACHTUNG: Ersetzt die aktuelle Datenbank – erfordert getippte Bestätigung."""
    if request.form.get('confirm_text', '').strip() != 'WIEDERHERSTELLEN':
        flash('Bestätigung fehlgeschlagen – bitte exakt "WIEDERHERSTELLEN" eingeben.', 'danger')
        return redirect(url_for('admin_backups_list'))

    backups_dir = os.path.join(os.path.dirname(__file__), 'backups')
    safe_name = os.path.basename(filename)  # Schutz vor Path-Traversal
    backup_path = os.path.join(backups_dir, safe_name)
    if not os.path.exists(backup_path) or not backup_path.startswith(backups_dir):
        flash('Backup-Datei nicht gefunden.', 'danger')
        return redirect(url_for('admin_backups_list'))

    live_db_path = _resolve_live_db_path()
    if not live_db_path or not os.path.exists(live_db_path):
        flash(f'Aktuelle Datenbankdatei konnte nicht ermittelt werden. '
              f'Versuchter Pfad: {live_db_path or "kein Kandidat gefunden"}. '
              f'Bitte prüfen, ob die Datei dort tatsächlich liegt, oder DATABASE_URL '
              f'in der .env kontrollieren.', 'danger')
        return redirect(url_for('admin_backups_list'))

    import tarfile, tempfile, glob as _glob, shutil

    try:
        with tempfile.TemporaryDirectory() as tmp_extract:
            with tarfile.open(backup_path, 'r:gz') as tf:
                _safe_extractall(tf, tmp_extract)          # Build ab: kein Ausbrechen aus dem Zielordner

            sqlite_files = _glob.glob(os.path.join(tmp_extract, '*.sqlite'))
            if not sqlite_files:
                flash('Im Backup wurde keine Datenbank-Datei gefunden.', 'danger')
                return redirect(url_for('admin_backups_list'))
            backup_db = sqlite_files[0]

            # 1. Sicherheitskopie der AKTUELLEN Datenbank anlegen (vor jedem Restore)
            os.makedirs(backups_dir, exist_ok=True)
            pre_restore_name = f'pre_restore_{datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")}.db'
            shutil.copy2(live_db_path, os.path.join(backups_dir, pre_restore_name))

            # 2. Alle DB-Verbindungen schließen, bevor die Datei ausgetauscht wird
            db.session.remove()
            db.engine.dispose()

            # 3. Atomarer Dateiwechsel: erst danebenkopieren, dann umbenennen
            #    (os.replace ist auf demselben Dateisystem atomar – kein
            #    Moment, in dem die Datei halb geschrieben/leer wäre)
            tmp_target = live_db_path + '.restoring'
            shutil.copy2(backup_db, tmp_target)
            os.replace(tmp_target, live_db_path)

            # 4. Alte WAL/SHM-Dateien der VORHERIGEN Datenbank entfernen – sie
            #    gehören zum alten Inhalt und dürfen nicht mit der neuen
            #    Datenbank vermischt werden
            for suffix in ('-wal', '-shm'):
                stale = live_db_path + suffix
                if os.path.exists(stale):
                    try:
                        os.remove(stale)
                    except OSError:
                        pass

            # 5. Uploads ergänzen (nur fehlende Dateien, nichts Neueres überschreiben)
            backup_uploads = os.path.join(tmp_extract, 'static', 'uploads')
            restored_files = 0
            if os.path.isdir(backup_uploads):
                live_uploads = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
                for root, _dirs, files in os.walk(backup_uploads):
                    rel = os.path.relpath(root, backup_uploads)
                    target_dir = os.path.join(live_uploads, rel) if rel != '.' else live_uploads
                    os.makedirs(target_dir, exist_ok=True)
                    for fname in files:
                        src_f = os.path.join(root, fname)
                        dst_f = os.path.join(target_dir, fname)
                        if not os.path.exists(dst_f):
                            try:
                                shutil.copy2(src_f, dst_f)
                                restored_files += 1
                            except OSError:
                                pass

        # 6. Passenger-Neustart auslösen, damit alle Worker die neue DB sauber laden
        try:
            tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            with open(os.path.join(tmp_dir, 'restart.txt'), 'w') as f:
                f.write(datetime.utcnow().isoformat())
            restart_note = ' Die App wurde zum Neustart aufgefordert.'
        except Exception:
            restart_note = ' Bitte die App JETZT manuell in Plesk neu starten!'

        flash(f'Wiederherstellung erfolgreich! {restored_files} fehlende Datei(en) ergänzt. '
              f'Sicherheitskopie der vorherigen Datenbank: {pre_restore_name}.{restart_note}', 'success')
    except Exception as e:
        app.logger.error(f'Restore error: {e}', exc_info=True)
        flash(f'Fehler bei der Wiederherstellung: {e}', 'danger')

    return redirect(url_for('admin_backups_list'))


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
    # Build w: Fahrzeit (nur Touren mit Zeitstempeln im GPX) und streckengewichtetes Ø-Tempo
    total_moving_s = sum(t.gpx_moving_s for t in tours if t.gpx_moving_s)
    km_timed       = sum(t.gpx_km for t in tours if t.gpx_moving_s and t.gpx_km)
    avg_kmh_year   = round(km_timed / (total_moving_s / 3600), 1) if total_moving_s else None
    # Fotozählung in einer Abfrage statt N+1
    photo_counts = dict(db.session.query(
        TourPhoto.tour_id, db.func.count(TourPhoto.id)
    ).filter(TourPhoto.tour_id.in_([t.id for t in tours]))
     .group_by(TourPhoto.tour_id).all())
    total_photos = sum(photo_counts.values())

    # Participation count per user this year – Build ab: eine Abfrage statt einer je Tour
    tour_ids = [t.id for t in tours]
    part_counts = dict(db.session.query(TourParticipant.user_id, db.func.count(TourParticipant.id))
                       .filter(TourParticipant.tour_id.in_(tour_ids),
                               TourParticipant.confirmed_present == True)          # noqa: E712
                       .group_by(TourParticipant.user_id).all()) if tour_ids else {}

    most_active = sorted(part_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    _users = {u.id: u for u in User.query.filter(User.id.in_([uid for uid, _ in most_active])).all()} if most_active else {}
    most_active = [(_users.get(uid), cnt) for uid, cnt in most_active if _users.get(uid)]
    # Teilnehmerzahl je Tour für die Liste (vorher t.attending_count = eine COUNT-Abfrage je Tour)
    attend_counts = dict(db.session.query(TourParticipant.tour_id, db.func.count(TourParticipant.id))
                         .filter(TourParticipant.tour_id.in_(tour_ids), TourParticipant.status == 'attending')
                         .group_by(TourParticipant.tour_id).all()) if tour_ids else {}

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
                           total_moving_s=total_moving_s, avg_kmh_year=avg_kmh_year,
                           total_photos=total_photos,
                           most_active=most_active,
                           monthly_json=monthly_json,
                           longest=longest,
                           attend_counts=attend_counts,
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
        current_user.large_text  = bool(request.form.get('large_text'))   # Build x
        current_user.bio         = request.form.get('bio','').strip() or None
        current_user.phone           = request.form.get('phone', '').strip()[:40] or None            # Build ab
        current_user.emergency_name  = request.form.get('emergency_name', '').strip()[:80] or None
        current_user.emergency_phone = request.form.get('emergency_phone', '').strip()[:40] or None
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
            if not current_user.check_password(request.form.get('current_password', '')):   # Build ab
                flash('Passwort nicht geändert: das aktuelle Passwort war falsch.', 'warning')
            elif pw == pw2 and len(pw) >= 8:
                current_user.set_password(pw)
                flash('Passwort geändert.', 'info')
            else:
                flash('Passwörter stimmen nicht überein oder zu kurz (mindestens 8 Zeichen).', 'warning')

        db.session.commit()
        flash('Profil gespeichert!', 'success')
        return redirect(url_for('my_profil'))
    cal_https, cal_webcal = _calendar_urls(current_user)              # Build w: Kalender-Abo
    return render_template('profil_edit.html', cal_https=cal_https, cal_webcal=cal_webcal)


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
    tour  = _photo_tour_or_404(photo)   # Audit 1.4.0: Gruppen-Check
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
    tour  = _tour_or_404(photo.tour_id)
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
    tour = _tour_or_404(tour_id)
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
    tour  = _photo_tour_or_404(photo)   # Audit 1.4.0: Gruppen-Check
    if not _can_edit_photo(photo, tour):
        abort(403)
    try:
        lat = float(request.form.get('lat', ''))
        lng = float(request.form.get('lng', ''))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            photo.lat = round(lat, 6)
            photo.lng = round(lng, 6)
            photo.gps_source = 'manual'                  # Build ac
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
    tour  = _photo_tour_or_404(photo)   # Audit 1.4.0: Gruppen-Check
    if not _can_edit_photo(photo, tour):
        abort(403)
    photo.lat = None
    photo.lng = None
    photo.gps_source = None                              # Build ac
    db.session.commit()
    flash('GPS-Daten entfernt.', 'success')
    return redirect(url_for('tour_detail', tour_id=photo.tour_id) + '#fotos')


@app.route('/touren/<int:tour_id>/fotos/platzieren', methods=['POST'])
@login_required
def tour_photos_place_on_track(tour_id):
    """Build ac: alle Fotos der Tour ohne Standort anhand ihrer Aufnahmezeit auf den GPX-Track
    setzen (braucht eine Aufzeichnung mit Zeitstempeln). offset_min gleicht eine falsch gehende
    Kamera-Uhr aus; bereits geschätzte Positionen werden dabei neu berechnet, echte (EXIF/manuell)
    bleiben unangetastet. action=undo entfernt alle geschätzten Positionen wieder."""
    tour = _tour_or_404(tour_id)
    if not _can_manage_tour(tour):
        abort(403)
    target = url_for('tour_detail', tour_id=tour_id) + '#fotos'
    if request.form.get('action') == 'undo':
        n = (TourPhoto.query.filter_by(tour_id=tour_id, gps_source='track')
             .update({'lat': None, 'lng': None, 'gps_source': None}, synchronize_session=False))
        db.session.commit()
        flash(f'{n} geschätzte Position(en) entfernt.', 'success' if n else 'info')
        return redirect(target)

    offset_min = max(-720, min(720, _parse_int(request.form.get('offset_min'), 0) or 0))
    timed = _tour_timed_points(tour)
    if not timed:
        flash('Der GPX-Track dieser Tour hat keine Zeitstempel (geplante Route statt Aufzeichnung) – '
              'automatisches Platzieren geht nur mit einer Aufzeichnung. Du kannst die Positionen '
              'per ✏️ am Foto auf der Karte setzen.', 'warning')
        return redirect(target)
    photos = TourPhoto.query.filter_by(tour_id=tour_id).all()
    placed, no_time, outside = _place_photos_on_track(photos, timed, offset_min)
    db.session.commit()
    parts = [f'📍 {placed} Foto(s) auf der Strecke platziert (geschätzt)']
    if offset_min:
        parts.append(f'Zeitkorrektur {offset_min:+d} min')
    if no_time:
        parts.append(f'{no_time} ohne Aufnahmezeit')
    if outside:
        parts.append(f'{outside} außerhalb der Aufzeichnung ({_timed_range_text(timed)})')
    flash(' – '.join(parts), 'success' if placed else 'warning')
    if outside and not placed:
        hint = _suggest_offset(photos, timed, offset_min)
        if hint:
            flash(hint, 'info')
    return redirect(target)


def _suggest_offset(photos, timed_points, offset_min=0):
    """Build ac: Liegen alle Fotos außerhalb der Aufzeichnung, aber mit einer typischen Zeitzonen-
    Verschiebung (±1 h, ±2 h) innerhalb, dann hat die App vermutlich Ortszeit statt UTC in den GPX
    geschrieben (oder die Kamera-Uhr steht falsch). Liefert einen Hinweistext mit der passenden
    Zeitkorrektur oder None."""
    candidates = [p for p in photos if p.taken_at and not (p.has_gps and p.gps_source != 'track')]
    if not candidates:
        return None
    best, best_n = None, 0
    for delta in (-120, -60, 60, 120):
        n = sum(1 for p in candidates if _track_position_at(timed_points, p.taken_at, offset_min + delta))
        if n > best_n:
            best, best_n = offset_min + delta, n
    if not best_n:
        return None
    return (f'Hinweis: Mit Zeitkorrektur {best:+d} min lägen {best_n} Foto(s) in der Aufzeichnung – '
            f'vermutlich schreibt die Aufzeichnungs-App Ortszeit statt Weltzeit (UTC) in den GPX, oder die '
            f'Kamera-Uhr geht falsch. Einfach {best:+d} ins Feld „Zeitkorrektur“ eintragen und erneut platzieren.')


def _timed_range_text(timed_points):
    """'14.06.2025 08:00–11:20 Uhr' für die Spanne einer Aufzeichnung (Ortszeit)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo('Europe/Berlin')
        a = datetime.fromtimestamp(timed_points[0][0], tz)
        b = datetime.fromtimestamp(timed_points[-1][0], tz)
        return f"{a.strftime('%d.%m.%Y %H:%M')}–{b.strftime('%H:%M')} Uhr"
    except Exception:
        return '?'



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
        from PIL import Image as PILImage, ImageOps
        img = PILImage.open(f)
        img = ImageOps.exif_transpose(img)      # Build f: Handy-Fotos richtig drehen (EXIF geht beim Speichern verloren)
        img.thumbnail((256, 256))
        if ext in ('jpg', 'jpeg') and img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
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
            'telegram_invite_link', 'whatsapp_group_link', 'contact_email',
            'default_start_time', 'default_meeting_desc',
            'default_meeting_lat', 'default_meeting_lng',
            'morning_opener_until', 'site_name', 'base_url',
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
    if len(pw) < 8:
        flash('Passwort muss mindestens 8 Zeichen haben.', 'danger')
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
    _photo_tour_or_404(photo)   # Audit 1.4.0: Gruppen-Check
    if photo.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], photo.filename)
    lat, lng = extract_gps_from_exif(path)
    if lat and lng:
        photo.lat = lat
        photo.lng = lng
        photo.gps_source = 'exif'                        # Build ac
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


@app.route('/gruppe/<int:group_id>/musik', methods=['POST'])
@login_required
def group_music_upload(group_id):
    """Standard-Hintergrundmusik für Tour-Videos einer Gruppe festlegen (nur Super-Admin)."""
    if current_user.role != 'admin':
        abort(403)
    group = Group.query.get_or_404(group_id)
    music_file = request.files.get('default_music')
    if not music_file or not music_file.filename:
        flash('Keine Datei ausgewählt.', 'warning')
        return redirect(url_for('admin_groups'))
    ext = music_file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('mp3', 'aac', 'm4a', 'wav', 'ogg'):
        flash('Nur MP3, AAC, M4A, WAV oder OGG erlaubt.', 'danger')
        return redirect(url_for('admin_groups'))

    music_dir = os.path.join(app.root_path, 'static', 'uploads', 'group_music')
    os.makedirs(music_dir, exist_ok=True)

    if group.default_music:
        old_path = os.path.join(music_dir, group.default_music)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass

    music_fname = f'group_{group.id}_{secrets.token_hex(6)}.{ext}'
    music_path  = os.path.join(music_dir, music_fname)
    music_file.save(music_path)
    group.default_music = music_fname
    db.session.commit()
    flash(f'Standardmusik für „{group.name}" gesetzt.', 'success')
    return redirect(url_for('admin_groups'))


@app.route('/gruppe/<int:group_id>/musik/loeschen', methods=['POST'])
@login_required
def group_music_delete(group_id):
    """Entfernt die Standardmusik einer Gruppe wieder."""
    if current_user.role != 'admin':
        abort(403)
    group = Group.query.get_or_404(group_id)
    if group.default_music:
        music_dir = os.path.join(app.root_path, 'static', 'uploads', 'group_music')
        old_path = os.path.join(music_dir, group.default_music)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass
        group.default_music = None
        db.session.commit()
        flash('Standardmusik entfernt.', 'success')
    return redirect(url_for('admin_groups'))


@app.route('/gruppe/<int:group_id>/umbenennen', methods=['POST'])
@login_required
def group_rename(group_id):
    """Name und Beschreibung einer Gruppe ändern (nur Super-Admin)."""
    if current_user.role != 'admin':
        abort(403)
    group = Group.query.get_or_404(group_id)
    new_name = request.form.get('name', '').strip()
    new_desc = request.form.get('description', '').strip()
    if not new_name:
        flash('Name darf nicht leer sein.', 'danger')
        return redirect(url_for('admin_groups'))
    old_name = group.name
    group.name = new_name
    group.description = new_desc or None
    db.session.commit()
    if old_name != new_name:
        flash(f'Gruppe „{old_name}" wurde in „{new_name}" umbenannt.', 'success')
    else:
        flash(f'Gruppe „{new_name}" aktualisiert.', 'success')
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
                _delete_tour_dependents(tour.id)   # Audit 1.4.0
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
    add_column('gastro_spots', 'hours_text', 'VARCHAR(300)')   # Build t: Öffnungszeiten-Text / Ruhetage
    add_column('gastro_spots', 'lunch',      'VARCHAR(10)')    # Build z: Mittagstisch yes/no/NULL
    add_column('gastro_spots', 'lunch_text', 'VARCHAR(200)')   # Build z: Mittagstisch-Details

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
    add_column('live_locations', 'speed',   'REAL')   # Build aa: Tempo (m/s) und Richtung (Grad)
    add_column('live_locations', 'heading', 'REAL')
    add_column('tours', 'cancel_reason', 'VARCHAR(200)')          # Build ab: Absage-Grund
    add_column('users', 'phone',           'VARCHAR(40)')          # Build ab: Telefon / Notfallkontakt
    add_column('users', 'emergency_name',  'VARCHAR(80)')
    add_column('users', 'emergency_phone', 'VARCHAR(40)')
    add_column('password_resets', 'purpose', 'VARCHAR(10)')       # Build ab: reset | login (Anmelde-Link)

    # ── Multi-Tenancy: Gruppen ────────────────────────────────────────────────
    # groups-Tabelle (Audit 1.4.0: eigene Verbindung – vorher wurde die bereits
    # geschlossene `conn` aus dem with-Block oben benutzt → Block lief nie durch)
    try:
        with db.engine.connect() as conn:
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
    try:
        with db.engine.connect() as _c2:
            default_gid = _c2.execute(text("SELECT id FROM groups LIMIT 1")).fetchone()
    except Exception:
        default_gid = None
    if default_gid:
        default_gid = default_gid[0]
        add_column('users',        'group_id', f'INTEGER DEFAULT {default_gid}')
        add_column('tours',        'group_id', f'INTEGER DEFAULT {default_gid}')
        add_column('invite_tokens','group_id', f'INTEGER DEFAULT {default_gid}')
        # Bestehende Zeilen zuordnen
        try:
            with db.engine.connect() as _c3:
                for table in ('users', 'tours', 'invite_tokens'):
                    try:
                        _c3.execute(text(f"UPDATE {table} SET group_id={default_gid} WHERE group_id IS NULL"))
                        _c3.commit()
                    except Exception:
                        pass
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
    add_column('tour_photos', 'orig_hash',  'VARCHAR(64)')
    add_column('tour_photos', 'gps_source', 'VARCHAR(10)')   # Build ac
    add_column('users', 'morning_opener_until', 'VARCHAR(5)')
    add_column('tours', 'approx_km',      'FLOAT')
    add_column('tours', 'external_link',  'VARCHAR(500)')
    add_column('tours', 'weather_json',   'TEXT')          # Build q: Wetter-Cache für den Tourtag
    add_column('tours', 'gpx_moving_s',   'INTEGER')       # Build w: Fahrzeit aus GPX-Zeitstempeln
    add_column('tours', 'gpx_avg_kmh',    'FLOAT')         # Build w: Ø-Tempo
    add_column('tours', 'gpx_preview',    'TEXT')          # Build w: Mini-Streckenvorschau (NULL = noch nicht berechnet)
    add_column('users', 'calendar_token', 'VARCHAR(40)')   # Build w: Kalender-Abo
    add_column('users', 'large_text', 'BOOLEAN DEFAULT 0') # Build x: Großschrift-Modus
    add_column('tours', 'gastro_spot_id', 'INTEGER')       # Build x: geplante Einkehr (Gastro-Eintrag)
    add_column('tours', 'einkehr_text', 'VARCHAR(200)')    # Build x: geplante Einkehr (Freitext)
    add_column('tours', 'attendance_reminded_at', 'DATETIME')  # Build x: Abend-Erinnerung „Wer war dabei?“
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
        # Audit 1.4.0: Gruppenwechsel per Session nur für Admins – andere bleiben in
        # ihrer eigenen Gruppe, auch wenn die Session einen anderen Wert enthält.
        if gid and not current_user.is_admin and current_user.group_id:
            gid = current_user.group_id
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
        _ensure_upload_htaccess()                      # Build v
        _db_migrated = True


# ── Selbst-Trigger für automatisches Backup (Fallback ohne Cronjob) ─────────
# Prüft nur mit geringer Wahrscheinlichkeit (~1 von 50 Requests), damit nicht
# bei jedem einzelnen Seitenaufruf ein DB-Zugriff für die Prüfung nötig ist.
# Reicht für eine aktive Gruppe locker aus, um ein fälliges Backup zeitnah
# auszulösen, ohne spürbare Last zu verursachen.
@app.before_request
def _self_trigger_backup():
    if request.endpoint in ('static', 'service_worker', 'api_backup_trigger'):
        return
    import random
    if random.random() > 0.02:  # ~2% Chance pro Request
        return
    try:
        due = _backup_is_due()
        if due:
            _start_backup_in_background(due, triggered_by='auto')   # Build ab: nicht mehr im Request
    except Exception as e:
        app.logger.warning(f'Self-trigger backup error: {e}')


# ── Selbst-Trigger für Tourtag-Erinnerung per Push ───────────────────────────
# Prüft mit geringer Wahrscheinlichkeit, ob heute eine Tour stattfindet, für
# die noch keine Morgen-Erinnerung verschickt wurde. Ein SiteConfig-Eintrag
# pro Tour+Datum verhindert Doppelversand, auch bei mehreren Anfragen.
def _send_morning_reminder_for_tour(tour):
    """Verschickt die Tourtag-Erinnerung (Telegram + Push) für eine einzelne
    Tour. Wiederverwendet vom automatischen Selbst-Trigger UND vom manuellen
    Admin-Test, damit beide garantiert denselben Nachrichtentext erzeugen."""
    attendee_ids = {p.user_id for p in
                    TourParticipant.query.filter_by(tour_id=tour.id, status='attending').all()}

    try:
        tg_msg = (
            f'⏰ <b>Heute ist Tourtag!</b>\n\n'
            f'🚴 <b>{_tg(tour.title)}</b>\n'
            f'{"🕐 " + _tg(tour.start_time) + " Uhr" + chr(10) if tour.start_time else ""}'
            f'👥 {len(attendee_ids)} Teilnehmer angemeldet\n'
        )
        if tour.meeting_desc:
            tg_msg += f'📍 Treffpunkt: {_tg(tour.meeting_desc)}\n'
        _ek = _tour_einkehr_text(tour)                 # Build x
        if _ek:
            tg_msg += f'☕ Einkehr: {_tg(_ek)}\n'
        tg_msg += f'\n👉 {app.config["BASE_URL"]}/touren/{tour.id}'
        send_telegram(tg_msg)
    except Exception as e:
        app.logger.warning(f'Telegram morning reminder failed: {e}')

    push_sent = 0
    if attendee_ids:
        body = f'Heute{" um " + tour.start_time + " Uhr" if tour.start_time else ""}: {tour.title}'
        if tour.meeting_desc:
            body += f' · {tour.meeting_desc}'
        if _ek:
            body += f' · Einkehr: {_ek}'
        for uid in attendee_ids:
            u = User.query.get(uid)
            if u:
                n, _ = send_push_to_user(u, title='🚴 Tour heute!', body=body, url=f'/touren/{tour.id}')
                push_sent += n
    return len(attendee_ids), push_sent


def _send_evening_reminder_for_tour(tour):
    """Build ab: Vorabend-Erinnerung „Morgen ist Tourtag“ – Telegram an die Gruppe,
    Push an Zugesagte und Unentschlossene (die sollen sich noch festlegen).
    Liefert (anzahl_empfänger, push_gesendet)."""
    rows = TourParticipant.query.filter(TourParticipant.tour_id == tour.id,
                                        TourParticipant.status.in_(['attending', 'maybe'])).all()
    attending = sum(1 for r in rows if r.status == 'attending')
    user_ids = [r.user_id for r in rows]
    _ek = _tour_einkehr_text(tour)
    try:
        tg_msg = (
            f'⏰ <b>Erinnerung: Morgen ist Tourtag!</b>\n\n'
            f'🚴 <b>{_tg(tour.title)}</b>\n'
            f'📅 {tour.tour_date.strftime("%d.%m.%Y") if tour.tour_date else "Datum offen"}'
            f'{" um " + _tg(tour.start_time) + " Uhr" if tour.start_time else ""}\n'
            f'👥 {attending} Teilnehmer angemeldet\n'
        )
        if tour.meeting_desc:
            tg_msg += f'📍 Treffpunkt: {_tg(tour.meeting_desc)}\n'
        if _ek:
            tg_msg += f'☕ Einkehr: {_tg(_ek)}\n'
        tg_msg += f'\n👉 {app.config["BASE_URL"]}/touren/{tour.id}'
        send_telegram(tg_msg)
    except Exception as e:
        app.logger.warning(f'Telegram evening reminder failed: {e}')

    push_sent = 0
    if user_ids:
        body = f'Morgen{" um " + tour.start_time + " Uhr" if tour.start_time else ""}: {tour.title}'
        if tour.meeting_desc:
            body += f' · {tour.meeting_desc}'
        for u in User.query.filter(User.id.in_(user_ids)).all():
            try:
                n, _ = send_push_to_user(u, title='📅 Morgen ist Tourtag!', body=body,
                                         url=f'/touren/{tour.id}')
                push_sent += n
            except Exception as e:
                app.logger.warning(f'evening push failed for user {u.id}: {e}')
    return len(user_ids), push_sent


def _run_tour_reminders(now=None):
    """Build ab: Tourtag- und Vorabend-Erinnerung prüfen und bei Fälligkeit verschicken.
    Beide laufen frühestens ab der im Admin einstellbaren Uhrzeit (Europe/Berlin) –
    vorher ging die Tourtag-Erinnerung kurz nach Mitternacht raus. Ein Tagesflag pro
    Art verhindert Doppelversand; ältere Flags werden dabei gelöscht.
    Liefert die Zahl der erinnerten Touren."""
    now = now or _berlin_now()
    today = now.date()
    done = 0

    if now.hour >= _cfg_int('reminder_morning_hour', 7, 0, 23):
        flag_key = f'morning_reminder_sent_{today.isoformat()}'
        if cfg(flag_key) != '1':
            for tour in Tour.query.filter(Tour.status == 'planned', Tour.tour_date == today).all():
                _send_morning_reminder_for_tour(tour)
                done += 1
            _set_day_flag('morning_reminder_sent_', flag_key)
            db.session.commit()

    if cfg('reminder_evening_enabled') != '0' and now.hour >= _cfg_int('reminder_evening_hour', 18, 0, 23):
        tomorrow = today + timedelta(days=1)
        flag_key = f'evening_reminder_sent_{tomorrow.isoformat()}'
        if cfg(flag_key) != '1':
            for tour in Tour.query.filter(Tour.status == 'planned', Tour.tour_date == tomorrow).all():
                _send_evening_reminder_for_tour(tour)
                done += 1
            _set_day_flag('evening_reminder_sent_', flag_key)
            db.session.commit()
    return done


@app.before_request
def _self_trigger_morning_reminder():
    if request.endpoint in ('static', 'service_worker', 'api_backup_trigger'):
        return
    import random
    if random.random() > 0.03:  # ~3% Chance pro Request
        return
    try:
        _run_tour_reminders()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f'Self-trigger tour reminder error: {e}')


@app.route('/archiv/suche')
@login_required
def archiv_suche():
    q      = request.args.get('q','').strip()
    year   = request.args.get('year','')
    diff   = request.args.get('diff','')

    # Build v: gemeinsame Auswahl mit dem GPX-ZIP-Download (archiv_gpx_zip)
    base      = _archiv_filter_query(q, year, diff)
    tours     = base.order_by(Tour.tour_date.desc()).all()
    gpx_total = base.filter(Tour.gpx_file != None).count()
    all_years = _archiv_years()

    tour_ids = [t.id for t in tours]
    part_counts = dict(db.session.query(
        TourParticipant.tour_id, db.func.count(TourParticipant.id)
    ).filter(TourParticipant.tour_id.in_(tour_ids),
             TourParticipant.confirmed_present == True
    ).group_by(TourParticipant.tour_id).all()) if tour_ids else {}
    photo_counts = dict(db.session.query(
        TourPhoto.tour_id, db.func.count(TourPhoto.id)
    ).filter(TourPhoto.tour_id.in_(tour_ids))
     .group_by(TourPhoto.tour_id).all()) if tour_ids else {}
    cover_photos = {}
    if tour_ids:
        for p_ in (TourPhoto.query.filter(TourPhoto.tour_id.in_(tour_ids))
                   .order_by(TourPhoto.tour_id,
                             db.text('COALESCE(sort_order, 999999) ASC'),
                             TourPhoto.taken_at.asc().nullslast()).all()):
            cover_photos.setdefault(p_.tour_id, p_)

    return render_template('touren/archiv.html', tours=tours,
                           q=q, year=year, diff=diff, all_years=all_years,
                           is_search=True, part_counts=part_counts,
                           photo_counts=photo_counts, cover_photos=cover_photos,
                           page=1, pages=1, total=len(tours), gpx_total=gpx_total)


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
    user = User.query.get_or_404(current_user.id)
    # Anonymize instead of hard-delete (keep tour participation count intact)
    _anonymize_user(user)
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
    """Einzelne Tour als .ics (Build w: gleiche Ereignis-Daten wie das Kalender-Abo, stabile UID,
    korrekt maskierte Sonderzeichen)."""
    tour = _tour_or_404(tour_id)
    stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    lines = (['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//De jungen Olen//Radgruppe//DE',
              'CALSCALE:GREGORIAN', 'METHOD:PUBLISH']
             + _ics_event_lines(tour, stamp) + ['END:VCALENDAR'])
    resp = make_response(_ics_join(lines))
    resp.headers['Content-Type'] = 'text/calendar; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename="tour_{tour.id}_{tour.tour_date}.ics"'
    return resp


# ─── Mitgliederverzeichnis (B-08) ────────────────────────────────────────────

@app.route('/mitglieder')
@login_required
def mitglieder():
    users = _gq(User).filter_by(is_active=True).order_by(User.name).all()
    # Build ab: Statistik für alle Mitglieder in einer Abfrage (vorher ~2 Abfragen je Mitglied)
    stats = badge_stats_bulk([u.id for u in users])
    members_data = []
    for u in users:
        st = stats.get(u.id, (0, 0.0))
        members_data.append({'user': u, 'tour_count': st[0],
                             'badges': compute_badges(u, stats=st)})
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
    # Audit 1.4.0: nur Fotos aus Touren der aktiven Gruppe (Mandanten-Trennung)
    from flask import g as _g
    _grp = getattr(_g, 'group', None)
    photo_q = TourPhoto.query.join(Tour, TourPhoto.tour_id == Tour.id)
    if _grp:
        photo_q = photo_q.filter(Tour.group_id == _grp.id)
    recent_photos = (photo_q
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
        f'Thema: <b>{_tg(theme)}</b>\n'
        f'{_tg(request.form.get("description",""))}\n\n'
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
    tour = _tour_or_404(tour_id)
    msg  = (
        f'📖 <b>Tour im Archiv</b>\n\n'
        f'🚴 <b>{_tg(tour.title)}</b>\n'
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
    # Build ab: Cache-Name trägt den Build – nach jedem Deploy holt sich der Browser frische
    # CSS/JS-Dateien statt bis zu 24 h alte aus dem Service-Worker-Cache.
    sw_path = os.path.join(app.static_folder, 'sw.js')
    try:
        with open(sw_path, encoding='utf-8') as f:
            body = f.read().replace('__BUILD__', re.sub(r'[^a-z0-9]+', '-', APP_BUILD.lower()))
    except OSError:
        abort(404)
    resp = make_response(body)
    resp.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


# ─── Phase 4: Tour-PDF (druckfreundliche Ansicht) ─────────────────────────────

@app.route('/touren/<int:tour_id>/drucken')
@login_required
def tour_print(tour_id):
    tour = _tour_or_404(tour_id)
    attending = TourParticipant.query.filter_by(tour_id=tour_id, status='attending').all()

    gpx_data = None
    if tour.gpx_file:
        gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], tour.gpx_file)
        if os.path.exists(gpx_path):
            gpx_data = gpx_for_page(gpx_path)          # Build ab: ≤ 2000 Punkte im Seiten-JSON

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


@app.route('/karte/erkundung')
@login_required
def explore_map():
    """'Unsere Landkarte': zeigt anhand aller gefahrenen GPX-Tracks, welche
    Kacheln (ca. 1×1 km bei unseren Breitengraden) die Gruppe schon 'erobert'
    hat – nach dem bekannten Strava-Kachel-Prinzip."""
    ZOOM = 14  # ca. 1-1.5 km Kachelgröße bei mitteleuropäischen Breitengraden

    tours = (_gq(Tour)
             .filter(Tour.status == 'completed', Tour.gpx_file != None)
             .all())

    visited_tiles = set()
    total_km = 0.0
    for t in tours:
        gpx_path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], t.gpx_file)
        if not os.path.exists(gpx_path):
            continue
        parsed = parse_gpx(gpx_path)
        if not parsed or not parsed.get('points'):
            continue
        if t.gpx_km:
            total_km += t.gpx_km
        # Jeden 4. Punkt reicht für die Kachel-Erkennung (Performance)
        for p in parsed['points'][::4]:
            visited_tiles.add(_tile_xy(p['lat'], p['lng'], ZOOM))

    tile_rects = [_tile_bounds(x, y, ZOOM) for x, y in visited_tiles]

    # Heimregion: 40km-Radius um den Standard-Treffpunkt, zur Prozent-Angabe
    home_lat = float(cfg('default_meeting_lat') or 52.9637)
    home_lng = float(cfg('default_meeting_lng') or 9.0891)
    home_x, home_y = _tile_xy(home_lat, home_lng, ZOOM)
    # Grobe Schätzung: wie viele Kacheln passen in einen 40km-Radius bei diesem Zoom
    import math
    km_per_tile = 111.32 * math.cos(math.radians(home_lat)) * (360 / (2**ZOOM)) / 1
    tiles_radius = max(1, int(40 / max(km_per_tile, 0.1)))
    total_region_tiles = (2*tiles_radius + 1) ** 2
    visited_in_region = sum(
        1 for (x,y) in visited_tiles
        if abs(x-home_x) <= tiles_radius and abs(y-home_y) <= tiles_radius
    )
    region_pct = round(100 * visited_in_region / total_region_tiles, 1) if total_region_tiles else 0

    return render_template('karte_erkundung.html',
                           tile_count=len(visited_tiles),
                           total_km=round(total_km, 1),
                           tour_count=len(tours),
                           region_pct=region_pct,
                           tile_rects_json=json.dumps(tile_rects),
                           home_lat=home_lat, home_lng=home_lng)


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
    """Touren von ungefähr diesem Tag (±3 Tage) in vergangenen Jahren,
    inkl. Titelfoto für einen ansprechenderen Rückblick."""
    try:
        from datetime import timedelta as _td
        today = date.today()
        tours = _gq(Tour).filter(
            Tour.status == 'completed',
            Tour.tour_date != None,
        ).order_by(Tour.tour_date.desc()).all()

        results = []
        for t in tours:
            if t.tour_date.year >= today.year:
                continue
            # Tag-genauer Vergleich (±3 Tage), Jahresgrenze berücksichtigen
            this_year_date = t.tour_date.replace(year=today.year)
            delta_days = abs((this_year_date - today).days)
            # Auch über Jahreswechsel hinweg prüfen (z.B. 30.12. vs 02.01.)
            delta_days = min(delta_days, 365 - delta_days)
            if delta_days > 3:
                continue

            cover = t.photos.order_by(
                db.text('COALESCE(sort_order, 999999) ASC'),
                TourPhoto.taken_at.asc().nullslast(),
                TourPhoto.created_at.asc()
            ).first()

            results.append({
                'tour': t,
                'years_ago': today.year - t.tour_date.year,
                'cover': cover,
            })
            if len(results) >= 3:
                break
        return results
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
        flash('Es ist ein Serverfehler aufgetreten. Bitte versuche es erneut.', 'danger')
        return render_template('errors/500.html'), 500
    except Exception:
        return f'<pre>500:\n{tb}</pre>', 500


# ─── Web-Ersteinrichtung (kein Shell-Zugriff nötig) ───────────────────────────
# Aufruf: https://deine-domain.de/setup/SETUP_KEY
# SETUP_KEY wird in der .env-Datei gesetzt.
# Die Route ist dauerhaft deaktiviert sobald ein Admin-Konto existiert.

@app.route('/setup', methods=['GET', 'POST'])   # Audit 1.4.0: POST fehlte → Formular ohne SETUP_KEY lief auf 405
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
    if len(pw) < 8:     errors.append('Passwort muss mindestens 8 Zeichen haben.')
    if User.query.filter_by(email=email).first():
        errors.append('Diese E-Mail ist bereits registriert.')

    if errors:
        return render_template('setup.html', step='form', key=key,
                               errors=errors, form=request.form)

    try:
        # Admin-User erstellen
        _default_grp = Group.query.order_by(Group.created_at).first()
        user = User(email=email, name=name, role='admin',
                   group_id=_default_grp.id if _default_grp else None)
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
    _default_grp = Group.query.order_by(Group.created_at).first()
    user = User(email=email, name=name, role='admin',
               group_id=_default_grp.id if _default_grp else None)
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
                try:
                    _cfg = _conn.execute(_text("SELECT value FROM site_config WHERE key='group_name'")).fetchone()
                except Exception:
                    _cfg = None  # Neuinstallation: site_config existiert noch nicht
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

            # default_music Spalte für bestehende groups-Tabelle nachrüsten
            try:
                _conn.execute(_text("ALTER TABLE groups ADD COLUMN default_music VARCHAR(150)"))
            except Exception:
                pass  # Spalte existiert bereits

            # visibility Spalte für bestehende announcements-Tabelle nachrüsten
            # (falls die Tabelle schon vor Einführung dieser Spalte angelegt wurde)
            try:
                _conn.execute(_text("ALTER TABLE announcements ADD COLUMN visibility VARCHAR(20) DEFAULT 'both'"))
            except Exception:
                pass  # Spalte existiert bereits oder Tabelle existiert noch nicht (wird gleich von db.create_all() angelegt)

            # orig_hash (Duplikat-Schutz Foto-Upload) direkt nachrüsten
            try:
                _conn.execute(_text("ALTER TABLE tour_photos ADD COLUMN orig_hash VARCHAR(64)"))
            except Exception:
                pass  # Spalte existiert bereits oder Tabelle wird gleich angelegt

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
