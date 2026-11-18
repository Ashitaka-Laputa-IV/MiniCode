Add `tests/slug.test.js` with at least five `node:test` tests for `slugify` from `src/slug.js`. Cover these cases:

- spaces become single hyphens;
- punctuation is collapsed into one hyphen;
- leading and trailing separators are trimmed;
- accented characters are folded to ASCII;
- the empty string returns an empty string.

Do not modify `src/slug.js`. Import the real `slugify` function, make the tests pass, and follow the style of the existing test. Run the tests.
