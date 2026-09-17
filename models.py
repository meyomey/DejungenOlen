from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Group(db.Model):
    """Eine Radgruppe mit eigenem Bereich, Mitgliedern und Touren."""
    __tablename__ = 'groups'
    id          = db.Column(db.Integer, primary_key=True)
    slug        = db.Column(db.String(40), unique=True, nullable=False)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    logo        = db.Column(db.String(120))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    is_active   = db.Column(db.Boolean, default=True)

    users   = db.relationship('User',        backref='group',  lazy='dynamic')
    tours   = db.relationship('Tour',        backref='group',  lazy='dynamic')
    invites = db.relationship('InviteToken', backref='group',  lazy='dynamic')

    @property
    def member_count(self):
        return self.users.filter_by(is_active=True).count()

    def __repr__(self):
        return f'<Group {self.slug}>'


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id           = db.Column(db.Integer, primary_key=True)
    email        = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name         = db.Column(db.String(80), nullable=False)
    nickname     = db.Column(db.String(40), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role         = db.Column(db.String(20), default='member')   # admin | organizer | member
    bicycle_type = db.Column(db.String(30), default='trekking') # rennrad | mtb | trekking | ebike
    is_ebike     = db.Column(db.Boolean, default=False)
    is_active    = db.Column(db.Boolean, default=True)
    group_id    = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    birthday     = db.Column(db.Date, nullable=True)
    bio          = db.Column(db.String(300), nullable=True)
    avatar       = db.Column(db.String(200), nullable=True)   # filename in uploads/avatars/
    morning_opener_until = db.Column(db.String(5), nullable=True)  # persönliche Frühöffner-Schwelle HH:MM
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_login   = db.Column(db.DateTime, nullable=True)

    participations = db.relationship('TourParticipant', back_populates='user', lazy='dynamic')
    photos         = db.relationship('TourPhoto', back_populates='user', lazy='dynamic')
    tours_created  = db.relationship('Tour', back_populates='creator', lazy='dynamic')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def display_name(self):
        return self.nickname or self.name

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_organizer(self):
        return self.role in ('admin', 'organizer')

    def get_id(self):
        return str(self.id)


class InviteToken(db.Model):
    __tablename__ = 'invite_tokens'
    id         = db.Column(db.Integer, primary_key=True)
    token      = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email      = db.Column(db.String(120), nullable=True)  # optional pre-fill
    label      = db.Column(db.String(100), nullable=True)   # Name/Notiz für den Admin
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    used       = db.Column(db.Boolean, default=False)
    group_id   = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by])


class Tour(db.Model):
    __tablename__ = 'tours'
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    tour_date   = db.Column(db.Date, nullable=True, index=True)   # None = Datum noch offen
    start_time  = db.Column(db.String(5), nullable=True)   # "HH:MM"
    approx_km   = db.Column(db.Float, nullable=True)        # ungefähre Länge
    external_link = db.Column(db.String(500), nullable=True) # Komoot/Strava/GPX-Link
    difficulty  = db.Column(db.String(20), default='mittel')
    status      = db.Column(db.String(20), default='planned', index=True)  # planned | completed | cancelled
    gpx_file    = db.Column(db.String(200), nullable=True)
    gpx_km      = db.Column(db.Float, nullable=True)
    gpx_ascent  = db.Column(db.Float, nullable=True)
    meeting_lat = db.Column(db.Float, nullable=True)
    meeting_lng = db.Column(db.Float, nullable=True)
    meeting_desc = db.Column(db.String(200), nullable=True)
    created_by  = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    group_id    = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    creator      = db.relationship('User', back_populates='tours_created')
    participants = db.relationship('TourParticipant', back_populates='tour',
                                   cascade='all, delete-orphan', lazy='dynamic')
    photos       = db.relationship('TourPhoto', back_populates='tour',
                                   cascade='all, delete-orphan', lazy='dynamic')

    @property
    def is_date_open(self):
        """True wenn kein echtes Datum gesetzt (Sentinel 9999-12-31)."""
        from datetime import date as _date
        return self.tour_date is None or self.tour_date == _date(9999, 12, 31)

    @property
    def attending_count(self):
        return self.participants.filter_by(status='attending').count()

    @property
    def difficulty_label(self):
        return {'leicht': 'Leicht', 'mittel': 'Mittel', 'schwer': 'Schwer'}.get(self.difficulty, self.difficulty)

    @property
    def difficulty_color(self):
        return {'leicht': 'success', 'mittel': 'warning', 'schwer': 'danger'}.get(self.difficulty, 'secondary')


class TourParticipant(db.Model):
    __tablename__ = 'tour_participants'
    id        = db.Column(db.Integer, primary_key=True)
    tour_id   = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False, index=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status    = db.Column(db.String(20), default='attending')  # attending | maybe | declined
    confirmed_present = db.Column(db.Boolean, default=False)   # set after tour
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tour = db.relationship('Tour', back_populates='participants')
    user = db.relationship('User', back_populates='participations')

    __table_args__ = (db.UniqueConstraint('tour_id', 'user_id'),)


class TourVideo(db.Model):
    """Hochgeladene MP4-Videos zu einer Tour."""
    __tablename__ = 'tour_videos'
    id          = db.Column(db.Integer, primary_key=True)
    tour_id     = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename    = db.Column(db.String(200), nullable=False)
    title       = db.Column(db.String(200), nullable=True)
    filesize    = db.Column(db.Integer, nullable=True)   # bytes
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    tour = db.relationship('Tour')
    user = db.relationship('User')


class TimeVote(db.Model):
    """Abstimmung über die Startzeit einer geplanten Tour."""
    __tablename__ = 'time_votes'
    id         = db.Column(db.Integer, primary_key=True)
    tour_id    = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    time_slot  = db.Column(db.String(5), nullable=False)   # "HH:MM"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('tour_id', 'user_id', 'time_slot'),)
    tour = db.relationship('Tour')
    user = db.relationship('User')


class PushSubscription(db.Model):
    """Web Push Subscription eines Nutzers."""
    __tablename__ = 'push_subscriptions'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    endpoint   = db.Column(db.Text, nullable=False, unique=True)
    p256dh     = db.Column(db.Text, nullable=False)
    auth       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user       = db.relationship('User')


class LiveLocation(db.Model):
    """Live-Standort eines Nutzers während einer Tour."""
    __tablename__ = 'live_locations'
    id         = db.Column(db.Integer, primary_key=True)
    tour_id    = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    lat        = db.Column(db.Float, nullable=False)
    lng        = db.Column(db.Float, nullable=False)
    accuracy   = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tour       = db.relationship('Tour')
    user       = db.relationship('User')
    __table_args__ = (db.UniqueConstraint('tour_id', 'user_id'),)


class RouteRating(db.Model):
    """Optionale Nutzerbewertung einer geplanten Route (gut / ok / schlecht)."""
    __tablename__ = 'route_ratings'
    id          = db.Column(db.Integer, primary_key=True)
    tour_id     = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating      = db.Column(db.String(10), nullable=False)  # good | ok | bad
    comment     = db.Column(db.String(300), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('tour_id', 'user_id'),)
    tour = db.relationship('Tour')
    user = db.relationship('User')


class TourPhoto(db.Model):
    __tablename__ = 'tour_photos'
    id         = db.Column(db.Integer, primary_key=True)
    tour_id    = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename   = db.Column(db.String(200), nullable=False)
    caption    = db.Column(db.String(200), nullable=True)
    lat        = db.Column(db.Float, nullable=True)
    lng        = db.Column(db.Float, nullable=True)
    taken_at   = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sort_order = db.Column(db.Integer, nullable=True, default=None)

    tour = db.relationship('Tour', back_populates='photos')
    user = db.relationship('User', back_populates='photos')

    @property
    def has_gps(self):
        return self.lat is not None and self.lng is not None


class GastroSpot(db.Model):
    """Gastronomie-Eintrag – Café, Kneipe, Bäckerei etc."""
    __tablename__ = 'gastro_spots'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    spot_type   = db.Column(db.String(30), default='cafe')  # cafe|kneipe|baeckerei|restaurant|imbiss|other
    address     = db.Column(db.String(200), nullable=True)
    lat         = db.Column(db.Float, nullable=False)
    lng         = db.Column(db.Float, nullable=False)
    opens_at    = db.Column(db.String(5), nullable=True)   # "HH:MM"
    closes_at   = db.Column(db.String(5), nullable=True)
    phone       = db.Column(db.String(30), nullable=True)
    website     = db.Column(db.String(200), nullable=True)
    notes       = db.Column(db.Text, nullable=True)
    osm_id      = db.Column(db.String(30), nullable=True)  # track OSM-imported entries
    added_by    = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    reviews     = db.relationship('GastroReview', back_populates='spot',
                                   cascade='all, delete-orphan', lazy='dynamic')
    creator     = db.relationship('User', foreign_keys=[added_by])

    @property
    def type_label(self):
        return {
            'cafe':       '☕ Café',
            'kneipe':     '🍺 Kneipe/Gasthaus',
            'baeckerei':  '🥐 Bäckerei',
            'restaurant': '🍽️ Restaurant',
            'imbiss':     '🥪 Imbiss',
            'other':      '📍 Sonstiges',
        }.get(self.spot_type, self.spot_type)

    @property
    def is_morning_friendly(self):
        """True if opens before the configured morning threshold."""
        if not self.opens_at:
            return None
        try:
            from models import SiteConfig
            threshold = SiteConfig.get('morning_opener_until', '09:30')
            h_t, m_t = map(int, threshold.split(':'))
            h, m = map(int, self.opens_at.split(':'))
            return (h * 60 + m) <= (h_t * 60 + m_t)
        except Exception:
            return None

    @property
    def avg_rating(self):
        reviews = self.reviews.all()
        if not reviews:
            return None
        scores = [r.score for r in reviews if r.score]
        return round(sum(scores) / len(scores), 1) if scores else None


class GastroReview(db.Model):
    __tablename__ = 'gastro_reviews'
    id         = db.Column(db.Integer, primary_key=True)
    spot_id    = db.Column(db.Integer, db.ForeignKey('gastro_spots.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    score      = db.Column(db.Integer, nullable=True)   # 1–5
    emoji      = db.Column(db.String(4),  nullable=True)   # 👍 👎 ☕
    note       = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    spot = db.relationship('GastroSpot', back_populates='reviews')
    user = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('spot_id', 'user_id'),)


class GastroPhoto(db.Model):
    """Fotos zu Gastro-Spots."""
    __tablename__ = 'gastro_photos'
    id         = db.Column(db.Integer, primary_key=True)
    spot_id    = db.Column(db.Integer, db.ForeignKey('gastro_spots.id'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename   = db.Column(db.String(200), nullable=False)
    caption    = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    spot = db.relationship('GastroSpot', backref=db.backref('photos', lazy='dynamic'))
    user = db.relationship('User')


class POI(db.Model):
    """Points of Interest: Pausenorte, Lieblingsorte, Treffpunkte."""
    __tablename__ = 'pois'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    category    = db.Column(db.String(30), default='pausenort')
    # pausenort | lieblingsort | bank | brunnen | wc | aussicht | reparatur
    lat         = db.Column(db.Float, nullable=False)
    lng         = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_shared   = db.Column(db.Boolean, default=True)   # False = nur eigene Ansicht
    added_by    = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    creator     = db.relationship('User', foreign_keys=[added_by])

    @property
    def category_icon(self):
        return {
            'pausenort':  '☕',
            'lieblingsort': '❤️',
            'bank':       '🪑',
            'brunnen':    '💧',
            'wc':         '🚻',
            'aussicht':   '🏔️',
            'reparatur':  '🔧',
        }.get(self.category, '📍')

    @property
    def category_label(self):
        return {
            'pausenort':  'Pausenort',
            'lieblingsort': 'Lieblingsort',
            'bank':       'Bank/Sitzgelegenheit',
            'brunnen':    'Brunnen/Wasser',
            'wc':         'WC',
            'aussicht':   'Aussichtspunkt',
            'reparatur':  'Fahrrad-Reparatur',
        }.get(self.category, self.category)


class TourComment(db.Model):
    """Kommentare auf Tourendetailseiten."""
    __tablename__ = 'tour_comments'
    id         = db.Column(db.Integer, primary_key=True)
    tour_id    = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    parent_id  = db.Column(db.Integer, db.ForeignKey('tour_comments.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tour    = db.relationship('Tour')
    user    = db.relationship('User')
    replies = db.relationship('TourComment', lazy='dynamic',
                               foreign_keys=[parent_id])


class PasswordReset(db.Model):
    __tablename__ = 'password_resets'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    token      = db.Column(db.String(64), unique=True, nullable=False)
    used       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')


class SiteConfig(db.Model):
    """Admin-configurable key/value settings stored in DB."""
    __tablename__ = 'site_config'
    key   = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=True)

    # Convenience class methods
    @classmethod
    def get(cls, key, default=None):
        row = cls.query.get(key)
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        row = cls.query.get(key)
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))
        db.session.commit()

    # ── Default values ───────────────────────────────────────────────────────
    DEFAULTS = {
        'default_start_time':    '10:00',
        'default_meeting_desc':  'Dörphus Wulmstorf, Marschstraße 2, 27321 Thedinghausen-Wulmstorf',
        'default_meeting_lat':   '52.9637',
        'default_meeting_lng':   '9.0891',
        'morning_opener_until':  '09:30',  # Gastro filter threshold HH:MM
        'telegram_bot_token':    '',
        'telegram_chat_id':      '',
        'telegram_chat_username': '',      # @groupname for embed widget
        'telegram_invite_link':   '',      # https://t.me/+xxxx for private groups
        'site_name':             'De jungen Olen',
        'base_url':              '',
    }

