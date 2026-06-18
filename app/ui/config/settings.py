"""
Django settings for config project.

Production-aware: most security-sensitive values come from environment
variables. Local development continues to work without setting anything —
sensible fallbacks kick in when env vars are absent.
"""

import os
from pathlib import Path

import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# ── Secrets / debug / hosts ────────────────────────────────────────────────────

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-k)d^n))-847mgl#h7p9^&+6)=f^nc_=bdyf0i_)#hu3scraql@',
)

DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

# ALLOWED_HOSTS — comma-separated env var; defaults to local-dev hosts.
# On Render, set this to the rendered domain (e.g. 'my-app.onrender.com').
_default_hosts = 'localhost,127.0.0.1'
if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
    _default_hosts = f"{_default_hosts},{os.environ['RENDER_EXTERNAL_HOSTNAME']}"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', _default_hosts).split(',') if h.strip()]

# Django 4+ requires explicit CSRF trust for non-local form POST origins.
CSRF_TRUSTED_ORIGINS = [
    f"https://{host}" for host in ALLOWED_HOSTS if host not in ('localhost', '127.0.0.1')
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'landing',
    't12_mapping',
]

# Workflow apps that use the pages/<page>/templates/ convention.
# Add new workflow names here (e.g. 'swot_analysis') and template discovery
# below picks them up automatically.
WORKFLOW_APPS = ['t12_mapping']

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise must come immediately after SecurityMiddleware so it can
    # serve collected static files in production without nginx in front.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

_TEMPLATE_DIRS = [BASE_DIR / 'templates']

# Auto-discover per-page templates: <workflow>/pages/<page>/templates/<page>/...
for _workflow in WORKFLOW_APPS:
    _pages_root = BASE_DIR / _workflow / 'pages'
    if _pages_root.is_dir():
        for _page in _pages_root.iterdir():
            _tpl = _page / 'templates'
            if _tpl.is_dir():
                _TEMPLATE_DIRS.append(_tpl)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': _TEMPLATE_DIRS,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

# Reads DATABASE_URL if set (Render Postgres / Supabase / etc.); falls back
# to a local SQLite file for development.
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=os.environ.get('DATABASE_URL', '').startswith('postgres'),
    )
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# collectstatic target — gunicorn + whitenoise serves from here in production.
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Uploaded files and pipeline outputs.
# On Render with persistent disk, mount it at /var/data and set
# MEDIA_ROOT_PATH=/var/data. Locally and on free-tier Render this falls back
# to ./storage (ephemeral on free Render — uploads disappear on restart).
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT_PATH', BASE_DIR / 'storage'))
MEDIA_URL = '/storage/'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Behind Render's TLS-terminating proxy: tells Django the request was HTTPS
# even though gunicorn sees it as plain HTTP locally.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
