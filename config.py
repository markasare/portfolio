from pathlib import Path

from decouple import config


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = config("SECRET_KEY", default=config("FLASK_SECRET_KEY", default="dev-secret-key-change-in-production"))

    EMAIL_PROVIDER = config("EMAIL_PROVIDER", default="ses")
    EMAIL_FROM = config("EMAIL_FROM", default="no-reply@markasare.com")
    CONTACT_OWNER_EMAIL = config("CONTACT_OWNER_EMAIL", default=config("SUPPORT_EMAIL", default=""))
    SUPPORT_EMAIL = config("SUPPORT_EMAIL", default=CONTACT_OWNER_EMAIL)
    ENABLE_AUTO_REPLY = config("ENABLE_AUTO_REPLY", default=True, cast=bool)

    MAIL_SERVER = config("MAIL_SERVER", default=config("SMTP", default="smtp.gmail.com"))
    MAIL_PORT = config("MAIL_PORT", default=config("PORT", default=587), cast=int)
    MAIL_USE_TLS = config("MAIL_USE_TLS", default=True, cast=bool)
    MAIL_USERNAME = config("MAIL_USERNAME", default=config("EMAIL_ADDRESS", default=""))
    MAIL_PASSWORD = config("MAIL_PASSWORD", default=config("EMAIL_PASSWORD", default=""))

    AWS_SES_REGION = config("AWS_SES_REGION", default="us-east-1")
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
    AWS_SESSION_TOKEN = config("AWS_SESSION_TOKEN", default="")

    VISITOR_ANALYTICS_TABLE = config("VISITOR_ANALYTICS_TABLE", default="")
    ANALYTICS_AWS_REGION = config("ANALYTICS_AWS_REGION", default=config("AWS_REGION", default="us-west-2"))
    ANALYTICS_COOKIE_NAME = config("ANALYTICS_COOKIE_NAME", default="visitor_id")
    ANALYTICS_COOKIE_MAX_AGE = config("ANALYTICS_COOKIE_MAX_AGE", default=60 * 60 * 24 * 365 * 2, cast=int)
    ANALYTICS_SESSION_WINDOW_SECONDS = config("ANALYTICS_SESSION_WINDOW_SECONDS", default=60 * 30, cast=int)
    ANALYTICS_READ_TOKEN = config("ANALYTICS_READ_TOKEN", default="")

    APP_BASE_URL = config("APP_BASE_URL", default="https://markasare.com")
    CONTACT_MIN_SUBMIT_SECONDS = config("CONTACT_MIN_SUBMIT_SECONDS", default=3, cast=int)
    CONTACT_MAX_SUBMIT_SECONDS = config("CONTACT_MAX_SUBMIT_SECONDS", default=60 * 60 * 2, cast=int)
    CONTACT_TURNSTILE_SITE_KEY = config("CONTACT_TURNSTILE_SITE_KEY", default="")
    CONTACT_TURNSTILE_SECRET_KEY = config("CONTACT_TURNSTILE_SECRET_KEY", default="")
    INDEX_FILE = str(BASE_DIR / "index.html")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}