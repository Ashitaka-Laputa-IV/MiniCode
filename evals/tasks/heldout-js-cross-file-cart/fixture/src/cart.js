import { formatMoney } from "./money.js";

export function cartTotal(items) {
  const cents = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  return formatMoney(cents);
}
