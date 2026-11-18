`app.duration.parse_duration` only handles a single component such as `45s`. It rejects combined durations such as `1h30m` and `2m15s`, but these should return the total number of seconds (`5400` and `135`).

Fix the parser so it accepts one or more `h`, `m`, and `s` components in that order, with an optional amount of surrounding whitespace, and returns the total seconds. Keep the current behavior for single components and keep raising `ValueError` for invalid input such as `10m30` (no trailing unit), `10x`, or text without a component. Run the tests.
