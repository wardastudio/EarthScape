import pytest
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


@pytest.fixture
def app():
    from config import Config

    class TestConfig(Config):
        TESTING = True
        JWT_ACCESS_TTL = 300
        JWT_REFRESH_TTL = 600

    from application import create_app
    app = create_app(TestConfig)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def valid_user_payload():
    return {
        "full_name": "Test User",
        "email": "testuser@earthscape.org",
        "phone": "+15551234567",
        "password": "Test@12345",
        "confirm_password": "Test@12345",
        "role": "researcher",
    }


@pytest.fixture
def login_payload():
    return {
        "email": "analyst@earthscape.org",
        "password": "Analyst@123",
    }
