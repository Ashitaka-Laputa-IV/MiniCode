# Security Policy

MiniCode is a local coding agent. It can read and write files and run shell
commands with the permissions of the user who starts it. It is **not a
sandbox**. This policy covers the MiniCode runtime, CLI, permission policy, and
evaluation harness.

## Supported versions

| Version | Supported |
| --- | --- |
| `0.1.x` development line (`0.1.0` in `pyproject.toml`) | Yes |
| Tagged releases | None yet |
| Older commits | No |

`main` and `dev` are development branches. Security fixes land on `dev` first
and are merged to `main` when ready. There are no tagged releases yet; use the
latest `dev` or `main` commit. Older commits are not supported.

## Reporting a vulnerability

Do not open a public issue for a security problem.

Email **Ashitaka-Laputa-IV@outlook.com** with the subject
`[SECURITY] MiniCode` and include the details listed below. If this repository
has GitHub private vulnerability reporting enabled, the Security tab's
**Report a vulnerability** form is preferred; use it instead of email when it is
available.

Include as much of the following as you can:

- affected commit, branch, or version
- operating system and Python version
- the exact MiniCode command or task
- the active permission mode and any shell allow-list
- expected behavior and actual behavior
- a minimal reproduction, if possible
- impact: host compromise, permission bypass, secret exposure, denial of
  service, or something else

We will acknowledge the report, reproduce it in a local workspace, and coordinate
a fix and disclosure timeline with you. Please do not test against systems or
accounts you do not own.

## Scope

In scope:

- bypassing `read-only` file or shell restrictions
- bypassing the hard deny-list
- executing a gated action in `ask` mode without approval
- exposing provider keys or other secrets through shell environment, logs,
  checkpoints, or tool output
- unintended host execution beyond the documented behavior
- escaping the evaluation harness so a fixture can affect the host or another
  task
- vulnerabilities in MiniCode's own code or workflows

Out of scope:

- expected destructive behavior in `yolo` mode for commands that are not on the
  hard deny-list
- running untrusted code without a container or VM
- vulnerabilities in third-party dependencies; report those upstream and we can
  track the fix
- how a model provider stores or processes prompts and responses
- prompt injection that does not bypass a control, expose secrets, or cause host
  compromise

## Threat model

MiniCode assumes that the workspace and the user are trusted by default. The
main threats are:

- a malicious or compromised repository containing instructions or code that
  induce unsafe tool calls
- prompt injection through files, tool output, or repository content
- a model that chooses a destructive or incorrect command
- accidental disclosure of secrets in the workspace
- a compromised dependency or provider integration
- an operator running the agent against untrusted code without isolation

The agent can read files under the workspace root, including `.env` and other
credentials that happen to be there. It can write files and execute shell
commands with the current user's OS permissions. File tools are not restricted
by `SHELL_ENV_ALLOWLIST`; that allow-list only filters the shell environment.

## Existing controls

- `read-only`, `ask`, and `yolo` permission modes
- human-in-the-loop approval for file writes, deletes, and risky shell commands
  in `ask` mode
- a hard deny-list for catastrophic commands in every mode
- a shell command allow-list, including `recommended` and `all`
- filtered shell environment that does not inherit provider keys
- `.env` loading limited to `MINICODE_MODEL` and known provider keys
- evaluation verification uses a filtered environment and keeps hidden tests
  outside the agent workspace
- MiniCode does not automatically commit, push, review, or merge; any such action
  must be a tool call and is subject to the active permission mode

See [`docs/permissions.md`](docs/permissions.md) for the decision order and the
exact enforcement points.

## Known limitations

- **Not a sandbox.** Permission modes and the hard deny-list are guardrails. A
  determined command can still reach the host.
- The hard deny-list is curated and incomplete. It does not model every shell,
  interpreter, or platform-specific destructive command.
- `yolo` skips approvals. Only the hard deny-list remains.
- File tools can read any file in the workspace, including `.env`.
- SQLite checkpoints contain conversation history and tool output. Treat
  `.minicode/checkpoints.sqlite` as sensitive data.
- Network access is not isolated. The policy can ask before known network
  commands, but it is not a network firewall.
- Evaluation hidden tests are hidden by convention, not by an adversarial
  sandbox.
- The policy classifies command text; it is not a full shell parser. Allowed
  commands can still have side effects.

## Safe usage

- Run MiniCode in a container or VM when working with untrusted repositories,
  generated code, or untrusted task input.
- Use a dedicated, least-privilege OS user and workspace.
- Use a dedicated provider key with a spending limit; rotate it if exposed.
- Prefer `read-only` for review tasks and `ask` for normal edits. Avoid `yolo`
  on untrusted code.
- Review the commands and diffs before approving them.
- Keep `.env` out of the workspace when possible. Remove credentials the agent
  does not need.
- Protect or delete `.minicode/checkpoints.sqlite` after working with sensitive
  repositories.
- Restrict network egress at the container or host level if the task does not
  need network access.
- Keep dependencies up to date and review lock-file changes.

## Disclosure

We will coordinate disclosure with the reporter. Please allow time for a fix
and a release before publishing details. Credit is available on request.
