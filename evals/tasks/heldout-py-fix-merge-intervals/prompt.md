`app.intervals.merge_intervals` merges overlapping intervals but leaves touching intervals separate. For example, `merge_intervals([(1, 3), (3, 5)])` returns `[(1, 3), (3, 5)]` instead of `[(1, 5)]`.

Fix it so intervals that touch (the next start equals the current end) are merged as well. Keep the current behavior for overlapping, nested, unsorted, disjoint, empty, and single-interval inputs. Run the tests.
