Add `tests/test_inventory.py` with at least four pytest tests for `app.inventory.Inventory.reserve`. Cover these cases:

- reserving from an unknown SKU;
- a non-positive quantity;
- reserving all remaining stock;
- trying to reserve more than is available.

Do not change `app/inventory.py`. The tests should use the real `Inventory` class, run successfully, and follow the style of the existing tests. Run the tests.
