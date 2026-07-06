import os


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "lokalny-sekret-do-testow"
    )

    DATABASE_URL = os.environ.get("DATABASE_URL")

    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1
        )
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///crm_local.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "ziomeczki@fuszera.pl")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Fuszera_2023@")