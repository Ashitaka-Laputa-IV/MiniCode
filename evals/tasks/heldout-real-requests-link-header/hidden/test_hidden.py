from linkheader import parse_header_links


def test_url_with_comma_stays_one_link():
    links = parse_header_links(
        '<https://example.com/a,b>; rel="next", <https://example.com/c>; rel="last"'
    )

    assert len(links) == 2
    assert links[0] == {"url": "https://example.com/a,b", "rel": "next"}
    assert links[1] == {"url": "https://example.com/c", "rel": "last"}


def test_comma_url_in_the_middle_of_several_links():
    links = parse_header_links(
        '<https://example.com/1>; rel="prev", '
        '<https://example.com/a,b>; rel="next"; type="text/html", '
        '<https://example.com/3>; rel="last"'
    )

    assert len(links) == 3
    assert [link["url"] for link in links] == [
        "https://example.com/1",
        "https://example.com/a,b",
        "https://example.com/3",
    ]
    assert links[1]["rel"] == "next"
    assert links[1]["type"] == "text/html"


def test_query_string_with_comma_and_equals():
    links = parse_header_links(
        '<https://example.com/search?q=a,b&page=2>; rel="next", '
        '<https://example.com/search?q=a,b&page=1>; rel="prev"'
    )

    assert [link["url"] for link in links] == [
        "https://example.com/search?q=a,b&page=2",
        "https://example.com/search?q=a,b&page=1",
    ]


def test_normal_headers_are_unchanged():
    links = parse_header_links(
        '<https://example.com/a>; rel="next"; type="image/jpeg",'
        '<https://example.com/b>; rel="last"'
    )

    assert links == [
        {"url": "https://example.com/a", "rel": "next", "type": "image/jpeg"},
        {"url": "https://example.com/b", "rel": "last"},
    ]


def test_single_link_is_unchanged():
    links = parse_header_links('<https://example.com/only>; rel="self"')

    assert links == [{"url": "https://example.com/only", "rel": "self"}]
