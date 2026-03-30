"""SQLAlchemy models for the MCP server.

Only User and KrogerOAuthToken are needed — the agent uses file-based
memory for everything else (receipts, shopping lists, etc.).
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "user"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    zip_code = Column(String(10), nullable=True)
    kroger_location_id = Column(String(100), nullable=True)
    preferences = Column(JSON, nullable=True)

    kroger_oauth_tokens = relationship("KrogerOAuthToken", back_populates="user")


class KrogerOAuthToken(Base):
    __tablename__ = "kroger_oauth_token"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("user.id"), nullable=False, index=True)
    access_token = Column(String(500), nullable=False)
    refresh_token = Column(String(500), nullable=False)
    token_type = Column(String(50), nullable=False, default="Bearer")
    expires_at = Column(DateTime, nullable=False)
    scope = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="kroger_oauth_tokens")
