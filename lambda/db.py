"""Synchronous SQLAlchemy session for Lambda (no asyncio event loop)."""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DATABASE_URL = os.environ["SYNC_DATABASE_URL"]

_engine = create_engine(_DATABASE_URL, pool_pre_ping=True, pool_size=2, max_overflow=2)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


@contextmanager
def get_session() -> Session:
    session = _SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
