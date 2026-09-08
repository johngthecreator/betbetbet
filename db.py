import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine

load_dotenv()

DB_URL = os.getenv("DB_URL")

engine = create_engine(DB_URL)
SQLModel.metadata.create_all(engine)
