from linkheader import parse_header_links


def test_two_normal_links():
    links = parse_header_links(
        '<https://example.com/a>; rel="next", <https://example.com/b>; rel="last"'
    )
    assert links == [
        {"url": "https://example.com/a", "rel": "next"},
        {"url": "https://example.com/b", "rel": "last"},
    ]


def test_no_space_after_comma():
    links = parse_header_links('<https://example.com/a>; rel="next",<https://example.com/b>')
    assert [link["url"] for link in links] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
