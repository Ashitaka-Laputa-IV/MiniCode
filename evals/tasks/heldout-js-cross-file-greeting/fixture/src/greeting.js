import { formatName } from "./format-name.js";

export function greeting(user) {
  return `Hello, ${formatName(user)}!`;
}
