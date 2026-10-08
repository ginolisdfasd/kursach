import os

PREFIX = os.environ.get("PREFIX", "library")
SCHEMA = os.environ.get("DB_SCHEMA", PREFIX)
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"postgresql://library:changeme@localhost:5432/{PREFIX}"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "changeme")
PAGE_SIZE_MAX = 100
