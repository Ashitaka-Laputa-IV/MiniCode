`linkheader.parse_header_links` is a minimized copy of `requests.utils.parse_header_links` from requests v2.4.3. It splits the `Link` header on every comma, so a URL that contains a comma is broken into two bogus links. For example, parsing

```text
<https://example.com/a,b>; rel="next", <https://example.com/c>; rel="last"
```

currently produces three links with a truncated URL instead of two links.

Fix the function so it only splits on a comma that is followed by `<`, optionally separated by spaces (for example with `re.split(", *<", value)`). Keep the current parameter parsing, quote stripping, and normal-header behavior unchanged. Run the tests.
