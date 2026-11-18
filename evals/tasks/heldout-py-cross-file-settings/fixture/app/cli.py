from .client import request_options


def describe(overrides=None):
    options = request_options(overrides)
    return f"retries={options['retries']} timeout={options['timeout']}"
