Add a `backoff` setting to the client configuration flow:

- `app.config.load_settings(overrides=None)` keeps the current `retries=2` and `timeout=30` defaults, and adds a `backoff=0.5` default. Overrides still win.
- `app.client.request_options(overrides=None)` includes the `backoff` value in its returned dict.
- `app.cli.describe(overrides=None)` includes the backoff value and returns `retries=<n> timeout=<n> backoff=<n>` in that order.

Keep the existing defaults and behavior unchanged, and run the tests.
