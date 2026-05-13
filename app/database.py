# Database connection and session management
import os
import re
import pymysql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "vps_api")

def get_database_url() -> str:
    return f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def validate_database_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(
            f"Invalid database name: {name!r}. "
            "Only letters, digits, and underscore are allowed."
        )
    return name

def create_database_if_not_exists() -> None:
    database_name = validate_database_name(DB_NAME)
    connection = pymysql.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        user=DB_USER,
        password=DB_PASS,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()

DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def main() -> None:
    import sys
    if len(sys.argv) == 2 and sys.argv[1] == "create-db":
        create_database_if_not_exists()
        print(f"Database '{DB_NAME}' is ready.")
        return
    print("Usage: python -m app.database create-db")
    raise SystemExit(1)

if __name__ == "__main__":
    main()
