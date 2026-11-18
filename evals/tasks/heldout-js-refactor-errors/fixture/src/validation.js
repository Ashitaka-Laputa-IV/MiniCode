export function parsePort(value) {
  if (typeof value !== "string" || !/^\d+$/.test(value)) {
    throw new TypeError("invalid port");
  }
  const port = Number(value);
  if (port < 1 || port > 65535) {
    throw new RangeError("port out of range");
  }
  return port;
}

export function parseTimeout(value) {
  if (typeof value !== "string" || !/^\d+$/.test(value)) {
    throw new TypeError("invalid timeout");
  }
  const timeout = Number(value);
  if (timeout < 0) {
    throw new RangeError("timeout out of range");
  }
  return timeout;
}
