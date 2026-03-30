"""Database engine and session setup."""

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.config import get_app_config

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

Base = declarative_base()


def _resolve_sqlite_url(url: str) -> str:
    """Make relative SQLite paths absolute against the project root."""
    if not url.startswith("sqlite:///"):
        return url
    db_path = Path(url[len("sqlite:///"):])
    if not db_path.is_absolute():
        db_path = (_PROJECT_ROOT / db_path).resolve()
    resolved = f"sqlite:///{db_path}"
    logger.info("Resolved database URL: %s", resolved)
    return resolved


def _get_database_url() -> str:
    try:
        config = get_app_config()
        url = config["database"]["url"]
    except Exception as e:
        logger.warning("Failed to load database URL from config: %s. Using default.", e)
        url = "sqlite:///./data/grocery.db"
    return _resolve_sqlite_url(url)


SQLALCHEMY_DATABASE_URL = _get_database_url()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
