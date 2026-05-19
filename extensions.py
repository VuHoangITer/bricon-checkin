import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()
engine = None
_SessionFactory = None


def init_engine(database_url: str):
    global engine, _SessionFactory
    engine = create_engine(database_url, pool_pre_ping=True, pool_size=5)
    _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def SessionLocal():
    if _SessionFactory is None:
        raise RuntimeError("Chua init_engine. Kiem tra DATABASE_URL trong .env")
    return _SessionFactory()