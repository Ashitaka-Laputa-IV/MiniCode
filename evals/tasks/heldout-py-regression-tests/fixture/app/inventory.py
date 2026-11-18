class Inventory:
    def __init__(self, counts=None):
        self._counts = dict(counts or {})

    def available(self, sku):
        return self._counts.get(sku, 0)

    def reserve(self, sku, quantity):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        available = self.available(sku)
        if quantity > available:
            raise ValueError("insufficient stock")
        self._counts[sku] = available - quantity
        return self._counts[sku]
