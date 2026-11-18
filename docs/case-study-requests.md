# Case study: fixing Link header parsing in a real `psf/requests` fixture

This case study uses a minimized, offline fixture from `psf/requests` to show how MiniCode
handles a real upstream bug, including HITL approval interrupts, a rejected command, a retry,
and final verification. It is a qualitative example, not a benchmark ranking.

## Upstream issue

`requests.utils.parse_header_links` split a `Link` header on every comma. That breaks valid
URLs that contain a comma inside `<...>`, for example:

```text
<https://example.com/a,b>; rel="next", <https://example.com/c>; rel="last"
```

The upstream bug and fix are:

- Issue: [psf/requests#2250](https://github.com/psf/requests/issues/2250)
- Fix PR: [psf/requests#2271](https://github.com/psf/requests/pull/2271)

The fixture is copied from `psf/requests` tag `v2.4.3`, commit
[`46d646064ca0836a7d7b4d50ea2c762d12ff8ce1`](https://github.com/psf/requests/commit/46d646064ca0836a7d7b4d50ea2c762d12ff8ce1),
file `requests/utils.py`. It is minimized to `parse_header_links` and retains the original
Apache-2.0 license and provenance in
[`evals/tasks/heldout-real-requests-link-header/PROVENANCE.md`](../evals/tasks/heldout-real-requests-link-header/PROVENANCE.md)
and [`LICENSE`](../evals/tasks/heldout-real-requests-link-header/LICENSE).

## Task setup

The agent receives only the fixture and visible tests. Hidden tests are copied in after the
agent stops, so they cannot be inspected or modified during the run. The prompt asks the agent
to split only on a comma followed by `<` (optionally followed by spaces) while preserving
normal headers, parameters, and quote stripping.

Task: `heldout-real-requests-link-header` in `evals/suites/heldout.toml`.

## Results

Both runs used `opencode-go:deepseek-v4.1-flash`.

| Baseline | Result | Tool calls | Approvals | Cost | Wall time |
|---|---:|---:|---:|---:|---:|
| `minicode-yolo` | 1/1 | 14 | 0 | $0.0031 | 81.6s |
| `minicode-ask` | 1/1 | 12 | 6 | $0.0021 | 50.5s |

The `minicode-ask` run is the case-study run because it exercises the approval path.

## Agent change

The agent added `import re` and changed the split:

```diff
-    for val in value.split(","):
+    for val in re.split(", *<", value):
```

This is the same behavioral fix as the upstream PR: split only when a comma is followed by
the start of the next `<...>` URL, not on commas inside a URL.

It also added a regression test:

```python
def test_url_containing_comma():
    links = parse_header_links(
        '<https://example.com/a,b>; rel="next", <https://example.com/c>; rel="last"'
    )
    assert links == [
        {"url": "https://example.com/a,b", "rel": "next"},
        {"url": "https://example.com/c", "rel": "last"},
    ]
```

## Approval interrupts and one rejected command

The `minicode-ask` run paused for approval six times. It read the fixture, made the edit, and
ran the existing tests. One attempt to reproduce the bug with `python -c ...` was rejected by
the eval approver because the command contained shell control characters and was not on the
scripted allow-list. The agent did not retry the same command. It instead added the regression
test through the file tools and ran the test suite with the approved `python -m pytest -q`
path.

The worker's visible test run ended with:

```text
3 passed
```

After the worker stopped, the hidden verification copied in its own tests and ended with
`5 passed`, so the change was accepted by both the visible regression and the held-out checks.

## Interpretation

- The agent found the minimal behavioral fix and matched the upstream change.
- The approval interrupts did not prevent completion; the agent adapted after the rejected
  command.
- The eval approver is a deterministic, cooperative test policy, not a human reviewer or a
  sandbox. It approves a narrow set of development commands and rejects shell control
  characters.
- This is one small fixture from one real repository. It shows a realistic repair flow, but it
  is not evidence of general SWE performance.

## Reproduce

```bash
uv run minicode eval --suite heldout \
  --baseline minicode-ask \
  --model opencode-go:deepseek-v4.1-flash \
  --task heldout-real-requests-link-header \
  --runs 1 --keep \
  --json evals/results/issue36-case-requests-ask.json
```

The `--keep` flag preserves the workspace so the diff and trace can be inspected.
