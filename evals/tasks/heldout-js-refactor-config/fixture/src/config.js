export function serverConfig(overrides = {}) {
  const config = { host: "localhost", port: 3000 };
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined) {
      config[key] = value;
    }
  }
  return config;
}

export function clientConfig(overrides = {}) {
  const config = { host: "localhost", timeout: 5000 };
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined) {
      config[key] = value;
    }
  }
  return config;
}
