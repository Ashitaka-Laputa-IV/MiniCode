Add a `short` option to the greeting flow:

- `formatName(user, { short = false } = {})` returns only `user.first` when `short` is true; otherwise it returns the current full name.
- `greeting(user, { short = false } = {})` forwards the option to `formatName`.
- Keep the default output and the existing exports from `src/index.js` unchanged.

Run the tests.
