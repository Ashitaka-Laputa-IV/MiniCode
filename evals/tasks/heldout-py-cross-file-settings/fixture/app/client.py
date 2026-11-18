from .config import load_settings


def request_options(overrides=None):
    settings = load_settings(overrides)
    return {"retries": settings["retries"], "timeout": settings["timeout"]}
