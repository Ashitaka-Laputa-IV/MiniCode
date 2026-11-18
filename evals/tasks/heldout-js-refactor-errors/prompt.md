`parsePort` and `parseTimeout` in `src/validation.js` duplicate the same "must be a string of digits" check.

Extract it into an exported helper named `parseInteger(value, name)`. It must return `Number(value)` for a string of digits, and otherwise throw `TypeError("invalid <name>")` using the supplied name. Call it from both public functions, keep their existing range checks, error types/messages, return values, and exports unchanged. Export `parseInteger` from `src/validation.js` and `src/index.js`, and run the tests.
