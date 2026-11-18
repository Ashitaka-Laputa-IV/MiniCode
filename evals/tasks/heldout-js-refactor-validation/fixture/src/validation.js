export function createAccount(input) {
  if (typeof input.email !== "string" || !input.email.includes("@")) {
    throw new TypeError("invalid email");
  }
  if (!Number.isInteger(input.age) || input.age < 0) {
    throw new TypeError("invalid age");
  }
  return { ...input };
}

export function updateAccount(account, input) {
  const updated = { ...account, ...input };
  if (typeof updated.email !== "string" || !updated.email.includes("@")) {
    throw new TypeError("invalid email");
  }
  if (!Number.isInteger(updated.age) || updated.age < 0) {
    throw new TypeError("invalid age");
  }
  return updated;
}
