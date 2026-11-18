from app.inventory import Inventory


def test_reserve_reduces_stock():
    inventory = Inventory({"apple": 3})
    assert inventory.reserve("apple", 2) == 1
    assert inventory.available("apple") == 1
