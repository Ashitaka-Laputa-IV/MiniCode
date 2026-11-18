from app.client import request_options
from app.cli import describe
from app.config import load_settings


def test_default_backoff():
    assert load_settings()["backoff"] == 0.5


def test_backoff_override_reaches_client_options():
    options = request_options({"timeout": 5, "backoff": 1.5})
    assert options == {"retries": 2, "timeout": 5, "backoff": 1.5}


def test_backoff_is_described():
    assert describe() == "retries=2 timeout=30 backoff=0.5"
    assert describe({"retries": 4, "backoff": 0.25}) == "retries=4 timeout=30 backoff=0.25"


def test_existing_defaults_are_unchanged():
    assert load_settings()["retries"] == 2
    assert load_settings()["timeout"] == 30
    assert request_options({"retries": 0}) == {"retries": 0, "timeout": 30, "backoff": 0.5}
