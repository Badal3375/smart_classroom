"""Django settings for the AI Smart Classroom Attendance System."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "apps.accounts", "apps.academics", "apps.biometrics", "apps.attendance", "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "apps.core.context_processors.globals",
    ]},
}]

# ---------------------------------------------------------------- Database
if os.getenv("DB_ENGINE", "sqlite").lower() == "mysql":
    import pymysql
    pymysql.version_info = (2, 2, 1, "final", 0)  # satisfy Django's mysqlclient version check
    pymysql.install_as_MySQLdb()
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "smart_attendance"),
        "USER": os.getenv("DB_USER", "root"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# PBKDF2-SHA256 (Django default) hashing; Argon2 can be prepended if argon2-cffi is installed.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ---------------------------------------------------------------- Security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8
CSRF_COOKIE_HTTPONLY = False  # JS reads token for AJAX frames
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)

# ---------------------------------------------------------------- Biometrics / AI
BIOMETRIC_ENCRYPTION_KEY = os.getenv("BIOMETRIC_ENCRYPTION_KEY", "")
FACE_BACKEND = os.getenv("FACE_BACKEND", "classical")
DEMO_MODE = env_bool("DEMO_MODE", True)

# Defaults for runtime-editable rules (overridden from Admin > System Settings)
DEFAULT_SYSTEM_SETTINGS = {
    "late_after_minutes": ("15", "Minutes after session start when a student is marked Late"),
    "min_attendance_percent": ("75", "Minimum attendance % before a warning is issued"),
    "late_counts_as_present": ("1", "1 = Late counts as attended in percentage, 0 = it does not"),
    "face_threshold": ("", "Cosine-similarity threshold for face match (blank = backend default)"),
    "face_high_confidence": ("0.70", "Face score at/above which face alone is accepted"),
    "face_low_confidence": ("0.12", "Face score below which person is Unknown (no iris fallback)"),
    "iris_hd_threshold": ("0.16", "Max fractional Hamming distance for an iris match (0.16 calibrated for demo data; use ~0.32 with real NIR iris cameras)"),
    "fusion_weight_face": ("0.6", "Weight of face score in multimodal fusion"),
    "fusion_weight_iris": ("0.4", "Weight of iris score in multimodal fusion"),
    "fusion_threshold": ("0.55", "Fused score required when iris verification is used"),
    "liveness_enabled": ("1", "Enable anti-spoofing checks (1/0)"),
    "correction_window_days": ("7", "Teachers may self-authorise corrections within N days; later needs Admin"),
    "semester_total_classes": ("40", "Planned classes per subject per semester (used for shortage prediction)"),
    "recognition_cooldown_seconds": ("5", "Ignore repeat detections of same student within N seconds"),
}
