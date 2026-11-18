from app.client import request_options
from app.cli import describe
from app.config import load_settings


def test_defaults():
    settings = load_settings()
    assert settings["retries"] == 2
    assert settings["timeout"] == 30
    assert request_options()["retries"] == 2
    assert request_options()["timeout"] == 30
    assert describe().startswith("retries=2 timeout=30")
