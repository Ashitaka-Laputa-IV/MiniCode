Add `tests/test_csv.py` with at least five pytest tests for `app.csv.parse_line`. Cover these cases:

- a quoted field that contains a comma;
- an escaped double quote inside a quoted field;
- empty fields, including a trailing empty field;
- spaces inside a field being preserved rather than trimmed;
- several quoted and unquoted fields in one line.

Do not change `app/csv.py`. Use the real `parse_line` function, make the tests pass, and follow the style of the existing tests. Run the tests.
