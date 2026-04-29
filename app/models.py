# Database models and SQLAlchemy setup for MariaDB
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

class MasterTokenStatus(enum.Enum):
    active = "active"
    revoked = "revoked"

class ContextStatus(enum.Enum):
    active = "active"
    closed = "closed"
    archived = "archived"

class MasterToken(Base):
    __tablename__ = "master_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(255), unique=True, nullable=False)
    description = Column(String(255))
    status = Column(Enum(MasterTokenStatus), default=MasterTokenStatus.active)
    created_at = Column(DateTime)
    tokens = relationship("Token", back_populates="issued_by_token")

class Token(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(255), unique=True, nullable=False)
    command_name = Column(String(255))
    command_params = Column(Text)  # Can be JSON string
    created_at = Column(DateTime)
    expires_at = Column(DateTime)
    issued_by = Column(Integer, ForeignKey("master_tokens.id"))
    usage_count = Column(Integer, default=0)
    max_uses = Column(Integer, default=1)
    last_used_at = Column(DateTime)
    context_id = Column(String(255))
    issued_by_token = relationship("MasterToken", back_populates="tokens")

class Context(Base):
    __tablename__ = "context"
    id = Column(Integer, primary_key=True, autoincrement=True)
    object_id = Column(String(255), unique=True, nullable=False)
    context_data = Column(Text)  # Arbitrary JSON as text
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    end_at = Column(DateTime, nullable=True)
    closed = Column(Boolean, default=False, nullable=False)

