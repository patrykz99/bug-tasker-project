import os
from urllib.parse import urlsplit

import pytest


test_database_url = os.getenv("TEST_DATABASE_URL")
if not test_database_url:
    raise pytest.UsageError(
        "Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test"
    )

parsed_database_url = urlsplit(test_database_url)
if not parsed_database_url.scheme.startswith("postgresql"):
    raise pytest.UsageError("TEST_DATABASE_URL must use PostgreSQL")
if not parsed_database_url.path.lower().endswith("_test"):
    raise pytest.UsageError("The PostgreSQL test database name must end in _test")

os.environ["DATABASE_URL"] = test_database_url

from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.main import Base, SessionLocal, Task, User, app, engine


@pytest.fixture
def clean_database():
    """Clean the dedicated test database before and after each test."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.execute(delete(Task))
        db.execute(delete(User))
        db.commit()

    yield

    with SessionLocal() as db:
        db.execute(delete(Task))
        db.execute(delete(User))
        db.commit()


@pytest.fixture
def client(clean_database):
    with TestClient(app) as test_client:
        yield test_client
