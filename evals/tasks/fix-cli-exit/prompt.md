`python -m app.cli --bad` currently exits 0. Unknown options must exit 2, print a usage/error message, and not print a traceback. Keep `python -m app.cli` working.
