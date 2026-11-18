`serverConfig` and `clientConfig` in `src/config.js` duplicate the same merging rule: start from the defaults and copy every override whose value is not `undefined`.

Extract it into an exported helper named `mergeDefined(defaults, overrides)` that returns a new object containing all defaults plus the defined overrides. Call it from both public functions, keep their defaults and behavior unchanged, and export `mergeDefined` from `src/config.js` and `src/index.js`. Run the tests.
