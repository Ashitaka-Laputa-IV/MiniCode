from app.records import normalize_email, normalize_name, user_record


def test_normalize_name():
    assert normalize_name("  Ada   Lovelace ") == "Ada Lovelace"
    assert normalize_name(None) == ""


def test_normalize_email():
    assert normalize_email(" ADA@Example.COM ") == "ada@example.com"
    assert normalize_email(None) == ""


def test_user_record():
    assert user_record(" Ada ", " ADA@Example.COM ") == {
        "name": "Ada",
        "email": "ada@example.com",
    }
