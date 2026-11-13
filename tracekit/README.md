# Tracekit policy mapping

MiniCode's Deep Agents tools (`execute`, `read_file`, `write_file`, ...) are
not in Tracekit's default tool map. The dev signer therefore classifies every
call as `TK-UNKNOWN-TOOL` and records it as `flag`.

`minicode-policy.yaml` maps them to Tracekit classes:

| MiniCode | Tracekit class |
| --- | --- |
| `execute` | `shell` |
| `read_file`, `write_file`, `edit_file`, `delete`, `ls`, `glob`, `grep` | `fs` |
| `write_todos`, `task` | `app` |

## Build the policy

Tracekit's dev signer always loads its bundled `dev.yaml`. Use a configured
signer with the mapped policy:

```powershell
uv run python scripts/build_tracekit_policy.py
```

This copies Tracekit's policy packs into `.minicode/tracekit/packs` and writes
the compiled policy to `.minicode/tracekit/minicode-policy.json`.

## Run the configured signer

```powershell
uv run tracekit signer serve --config tracekit/signer.example.yaml
```

In another shell, point MiniCode at its loopback endpoint:

```powershell
$ep = Get-Content .minicode\tracekit\signer\endpoint.json | ConvertFrom-Json
$env:TRACEKIT_SIGNER = "tcp://127.0.0.1:$($ep.port)"
$env:TRACEKIT_SIGNER_TOKEN = $ep.token
uv run minicode --audit "fix the tests"
```

## View and verify

```powershell
uv run tracekit view --config tracekit/signer.example.yaml --port 7779
uv run tracekit export --v2 --config tracekit/signer.example.yaml --last -o run.tkb
```

`tracekit view --config` reads the configured signer's data directory, not the
dev signer's. The endpoint token and signer state stay under `.minicode/`,
which is gitignored.

## Limits

This signer still runs as the same user, so it is evidence, not isolation. The
mapping changes policy classification (`allow` / `flag` / `deny`); it does not
replace MiniCode's permission modes or HITL approvals. A mapped command that
matches a Tracekit `ask` rule can still produce a Tracekit hold.
