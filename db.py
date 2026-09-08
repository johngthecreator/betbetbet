import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine

load_dotenv()

DB_URL = os.getenv("DB_URL")

# Railway's Postgres plugin hands out a plain postgresql:// URL. SQLAlchemy's
# create_engine defaults that scheme to the psycopg2 dialect, which isn't
# installed here (we use psycopg[binary], i.e. psycopg3) — force the psycopg3
# dialect explicitly instead of requiring a separately-formatted env var.
if DB_URL and DB_URL.startswith("postgresql://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DB_URL)
SQLModel.metadata.create_all(engine)
