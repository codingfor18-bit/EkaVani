import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent

# `neon env pull` writes the connection string at the project root. Keep
# supporting backend/.env for existing local development setups.
for env_file in (
    PROJECT_DIR / ".env.local",
    PROJECT_DIR / ".env",
    BACKEND_DIR / ".env",
):
    load_dotenv(env_file)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if os.getenv("REQUIRE_DATABASE_URL") == "1":
        raise RuntimeError("DATABASE_URL must be set for this deployment")
    DATABASE_URL = "sqlite:///./ekavani.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgres://")
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgresql://")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def ensure_assessment_details_column() -> None:
    """Add the assessment JSON to existing installs without losing history."""
    inspector = inspect(engine)
    if "practice_sessions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("practice_sessions")}
    if "assessment_details" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN assessment_details JSON")
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
