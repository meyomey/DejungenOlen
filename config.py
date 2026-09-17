import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    _secret = os.getenv('SECRET_KEY', '')
    SECRET_KEY = _secret if _secret else 'change-me-in-production-use-a-long-random-string'
    if not _secret:
        import warnings
        warnings.warn('⚠️  SECRET_KEY not set in .env – using insecure default!', stacklevel=2)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///dejungen_olen.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER_GPX    = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'gpx')
    UPLOAD_FOLDER_PHOTOS = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'photos')
    UPLOAD_FOLDER_AVATARS = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'avatars')
    MAX_CONTENT_LENGTH   = 500 * 1024 * 1024  # 500 MB (für Video-Uploads)
    # CSRF-Schutz via SameSite-Cookie (kein Flask-WTF nötig)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE  = 'Lax'
    SESSION_COOKIE_SECURE    = os.getenv('HTTPS', 'false').lower() == 'true'
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    # SQLite WAL-Modus für bessere Concurrency
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'timeout': 15},
        'pool_pre_ping': True,
    }

    ALLOWED_GPX_EXTENSIONS    = {'gpx'}
    ALLOWED_PHOTO_EXTENSIONS  = {'jpg', 'jpeg', 'png', 'heic', 'webp'}
    UPLOAD_FOLDER_VIDEOS      = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'videos')
    ALLOWED_VIDEO_EXTENSIONS  = {'mp4', 'mov', 'avi', 'mkv', 'm4v'}
    MAX_VIDEO_SIZE            = 500 * 1024 * 1024  # 500 MB

    # Telegram Bot (optional – leave empty to disable)
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')

    # App base URL for invite links
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')

    DIFFICULTY_CHOICES = [
        ('leicht',   'Leicht  (< 30 km, flach)'),
        ('mittel',   'Mittel  (30–60 km oder hügelig)'),
        ('schwer',   'Schwer  (> 60 km oder anspruchsvoll)'),
    ]
