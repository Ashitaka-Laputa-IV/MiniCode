def normalize_name(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def normalize_email(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def user_record(name, email):
    return {"name": normalize_name(name), "email": normalize_email(email)}
