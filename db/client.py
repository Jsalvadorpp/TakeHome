"""Postgres connection management.

Reads DATABASE_URL from a .env file (or the environment) and returns a connection.
This module is shared by the pipeline (for writing) and the API (for reading).

Usage:
    from db.client import get_connection

    conn = get_connection()
    # ... use conn ...
    conn.close()

.env file (place in the project root):
    DATABASE_URL=postgresql://user:password@localhost:5432/hail_db
"""

import os

import psycopg2
from dotenv import load_dotenv

# Load variables from .env into the environment.
# If .env doesn't exist, this does nothing (existing env vars are kept).
load_dotenv()


def get_connection():
    """Open and return a new Postgres connection.

    Reads the connection string from DATABASE_URL, which is loaded from .env
    (or already set in the environment).

    Example .env entry:
        DATABASE_URL=postgresql://postgres:secret@localhost:5432/hail_db

    Raises:
        RuntimeError: If DATABASE_URL is not set in .env or the environment.
        psycopg2.OperationalError: If the connection to Postgres fails.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to your .env file:\n"
            "  DATABASE_URL=postgresql://user:password@localhost:5432/hail_db"
        )
    return psycopg2.connect(url)