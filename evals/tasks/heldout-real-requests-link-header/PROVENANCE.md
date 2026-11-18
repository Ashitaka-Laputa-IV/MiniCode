# Provenance: `heldout-real-requests-link-header`

This task is a minimized fixture derived from the `psf/requests` repository.

- Source repository: <https://github.com/psf/requests>
- Source tag: `v2.4.3`
- Source commit: `46d646064ca0836a7d7b4d50ea2c762d12ff8ce1`
- Source file: `requests/utils.py`, function `parse_header_links`
- Raw source URL used:
  <https://raw.githubusercontent.com/psf/requests/v2.4.3/requests/utils.py>
- License: Apache License, Version 2.0. The full license text is in `LICENSE`.
  The upstream source file carries the same Apache-2.0 notice, which is kept
  in `fixture/linkheader.py`.
- Fixture generation: the single `parse_header_links` function was copied from
  `requests/utils.py` at tag `v2.4.3` and placed in `fixture/linkheader.py`,
  with the module docstring shortened and the upstream comment formatting
  retained. No other code from the repository is included.
- Upstream bug: <https://github.com/psf/requests/issues/2250>
- Upstream fix history: <https://github.com/psf/requests/pull/2271>

The bug is that the pre-fix function splits `Link` headers on every comma, so
a URL containing a comma is broken into bogus links. The expected fix splits
only on a comma followed by `<` (optionally with spaces), which keeps URLs
with commas intact while preserving normal header parsing.
