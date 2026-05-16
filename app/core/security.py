import re

import bcrypt


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=pwd_bytes, salt=salt)
    return hashed_password.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_byte_enc = plain_password.encode("utf-8")
    hashed_password_byte_enc = hashed_password.encode("utf-8")
    return bcrypt.checkpw(
        password=password_byte_enc,
        hashed_password=hashed_password_byte_enc,
    )


def validate_password_strength(val: str) -> str:
    """Validates that a password meets complexity requirements.

    These rules ensure high entropy and protect against brute-force attacks.
    Bcrypt has a 72-byte limit on password length which we enforce.
    """
    if len(val.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes long")
    if len(val) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", val):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", val):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", val):
        raise ValueError("Password must contain at least one number")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", val):
        raise ValueError("Password must contain at least one special character")
    return val
