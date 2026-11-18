`normalize_name` and `normalize_email` in `app/records.py` repeat the same handling for blank values: return `""` for `None`, otherwise convert to a string and strip surrounding whitespace.

Extract that shared step into a helper named `_field(value)`. It must return `""` for `None` and `str(value).strip()` otherwise. Both public functions must call `_field`, and their outputs must not change:

- `normalize_name` still collapses internal whitespace.
- `normalize_email` still lowercases the result.

Run the tests.
