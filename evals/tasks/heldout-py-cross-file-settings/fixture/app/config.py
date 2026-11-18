DEFAULTS = {"retries": 2, "timeout": 30}


def load_settings(overrides=None):
    settings = dict(DEFAULTS)
    settings.update(overrides or {})
    return settings
