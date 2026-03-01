from typing import Generator
from sqlmodel import Session
from app.core.db import engine

def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session and closes it after the request."""
    with Session(engine) as session:
        yield session
