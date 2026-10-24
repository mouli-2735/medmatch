import pytest
from unittest.mock import patch, MagicMock
from app.main import app
from app.auth import require_user
from app.db import init_db

@pytest.fixture(autouse=True)
def mock_smtp_in_all_tests():
    """Mock SMTP across all tests to prevent sending real emails."""
    with patch("smtplib.SMTP") as mock_smtp, patch("smtplib.SMTP_SSL") as mock_ssl:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance
        mock_ssl.return_value.__enter__.return_value = mock_instance
        yield mock_instance

@pytest.fixture(autouse=True)
def default_authenticated_user():
    """
    Provides default authenticated user override so existing clinical & pipeline
    tests keep passing seamlessly.
    """
    init_db()
    app.dependency_overrides[require_user] = lambda: {
        "id": "test_ph_sarah",
        "name": "Dr. Sarah",
        "email": "sarah@medmatch.test",
        "role": "pharmacist",
        "is_verified": 1
    }
    yield
    app.dependency_overrides.clear()
