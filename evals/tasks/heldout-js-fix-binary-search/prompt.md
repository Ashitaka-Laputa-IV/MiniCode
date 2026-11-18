`binarySearch` in `src/search.js` stops when `low` reaches `high`, so it never examines the last remaining element. For example, searching for `5` in `[1, 3, 5]` returns `-1`, and searching in a one-element array always misses.

Fix the loop so it checks the final candidate and returns the correct zero-based index. Keep the sorted-input assumption, the `-1` result for a missing value, and the existing empty-array behavior. Run the tests.
