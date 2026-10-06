import pytest

from app.core.auth import get_current_user
from app.main import app


@pytest.fixture(autouse=True)
def override_auth():
    """By default in unit tests, override auth to return 'admin'

    This allows previous phase tests to run hermetically without requiring JWT tokens.
    Authentication-specific tests in test_auth_and_security.py explicitly clear this override.
    """
    app.dependency_overrides[get_current_user] = lambda: "admin"
    yield
    app.dependency_overrides.pop(get_current_user, None)
