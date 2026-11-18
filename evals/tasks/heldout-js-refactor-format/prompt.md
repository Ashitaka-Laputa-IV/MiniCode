`formatDate` and `formatTime` in `src/format.js` repeat the same two-digit padding expression.

Extract it into an exported helper named `pad2(value)` that returns `String(value).padStart(2, "0")`. Both public functions must call the helper, their formatted output must stay the same, and `pad2` must be exported from `src/format.js` and `src/index.js`. Keep the existing exports and run the tests.
