import re

import bcrypt


def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using bcrypt.

    Encodes the input string to UTF-8 and uses `bcrypt.gensalt` to create
    a secure hash before decoding it back to a UTF-8 string.
    """
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=pwd_bytes, salt=salt)
    return hashed_password.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against a hashed representation.

    Encodes inputs to UTF-8, checks for bcrypt's 72-byte password limitation,
    and returns False on failure/type mismatches.
    """
    try:
        password_byte_enc = plain_password.encode("utf-8")
        hashed_password_byte_enc = hashed_password.encode("utf-8")

        if len(password_byte_enc) > 72:
            return False

        return bcrypt.checkpw(
            password=password_byte_enc,
            hashed_password=hashed_password_byte_enc,
        )
    except TypeError, ValueError:
        return False


def validate_password_strength(val: str) -> str:
    """
    Validates that a password meets length and complexity criteria.

    Raises:
        ValueError: If the password does not meet standard entropy and complexity rules
        (8-72 characters, containing uppercase, lowercase, numbers, and symbols).
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
