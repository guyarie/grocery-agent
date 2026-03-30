"""
Configuration module for the Agent Grocery MCP server.

Loads config/app.yaml with ${ENV_VAR} substitution, provides helpers
for database sessions and Kroger config.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root
_env_file = _PROJECT_ROOT / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
    logger.info("Loaded .env from %s", _env_file)

_config_cache: Dict[str, Any] = {}


def _substitute_env_vars(value: Any) -> Any:
    """Recursively replace ${VAR} with os.getenv(VAR)."""
    if isinstance(value, str):
        for var in re.findall(r"\$\{([^}]+)\}", value):
            value = value.replace(f"${{{var}}}", os.getenv(var, ""))
        return value
    if isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(i) for i in value]
    return value


def get_app_config() -> Dict[str, Any]:
    """Load and cache config/app.yaml with env-var substitution."""
    config_path = str(_PROJECT_ROOT / "config" / "app.yaml")
    if config_path in _config_cache:
        return _config_cache[config_path]

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not config:
        raise ValueError("Configuration file is empty")
    config = _substitute_env_vars(config)
    _config_cache[config_path] = config
    logger.info("Configuration loaded from %s", config_path)
    return config


def get_kroger_config() -> Dict[str, Any]:
    """Return the Kroger section with env-var overrides for credentials."""
    cfg = get_app_config()
    kroger = cfg.get("kroger", {}).copy()
    kroger["client_id"] = os.getenv("KROGER_CLIENT_ID", "")
    kroger["client_secret"] = os.getenv("KROGER_CLIENT_SECRET", "")
    if "test_user" in kroger:
        kroger["test_user"]["location_id"] = os.getenv("KROGER_TEST_LOCATION_ID", "")
    return kroger


def get_db_session():
    """Create and return a new SQLAlchemy session."""
    from src.database import SessionLocal
    return SessionLocal()


def get_user_id() -> str:
    """Return the default user ID for the single-user MVP."""
    return "default"
