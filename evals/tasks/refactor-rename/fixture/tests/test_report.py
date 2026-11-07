from app.report import summary


def test_summary():
    assert summary({"a": 2}) == "total=2"
