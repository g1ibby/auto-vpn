import pytest
from db.db import Database
from db.repository import Repository
import os
import tempfile

# Import your models directly
from db.models import Server, VPNPeer

@pytest.fixture(scope='function')
def test_db_path():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)  # Close the file descriptor as Peewee will manage the connection
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)

@pytest.fixture(scope='function')
def db_instance(test_db_path):
    """Initialize the Database instance with the test database."""
    db = Database()
    db.init_db(database_path=test_db_path)
    yield db
    db.db.close()

@pytest.fixture(scope='function')
def repository(db_instance):
    """Provide a Repository instance for tests."""
    # Reset the database before each test by dropping and recreating tables
    db_instance.db.drop_tables([Server, VPNPeer])
    db_instance.db.create_tables([Server, VPNPeer])
    return Repository()

