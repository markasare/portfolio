from pathlib import Path

from decouple import config


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = config("SECRET_KEY", default=config("FLASK_SECRET_KEY", default="dev-secret-key-change-in-production"))

    EMAIL_PROVIDER = config("EMAIL_PROVIDER", default="ses")
    EMAIL_FROM = config("EMAIL_FROM", default="no-reply@markasare.com")
    CONTACT_OWNER_EMAIL = config("CONTACT_OWNER_EMAIL", default="")
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

    APP_BASE_URL = config("APP_BASE_URL", default="https://markasare.com")
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