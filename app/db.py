import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")

# sqlite pragmas for better defaults
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

def _fk_pragma_on_connect(dbapi_con, con_record):
    try:
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)
if DATABASE_URL.startswith("sqlite"):
    try:
        from sqlalchemy import event
        event.listen(engine, "connect", _fk_pragma_on_connect)
    except Exception:
        pass
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
    future=True,
)
Base = declarative_base()


def get_session() -> Session:
    return SessionLocal()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

