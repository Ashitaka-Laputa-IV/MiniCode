def validate_email(email):
    return "@" in email and "." in email.split("@")[-1]


def create_user(email):
    if not validate_email(email):
        raise ValueError("invalid email")
    return {"email": email}


def update_user(user, email):
    if not validate_email(email):
        raise ValueError("invalid email")
    user["email"] = email
    return user
