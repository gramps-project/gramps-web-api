"""Password utility functions."""

import hashlib
import os


def generate_salt() -> bytes:
    """Generate a random salt."""
    return hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")


def hash_password_salt(password: str, salt: bytes) -> bytes:
    """Compute a password hash given a password and salt."""
    return hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000)


def hash_password(password: str) -> str:
    """Compute salted password hash."""
    salt = generate_salt()
    pw_hash = hash_password_salt(password, salt)
    return salt.decode("ascii") + pw_hash.hex()


def verify_password(password: str, salt_hash: str) -> bool:
    """Verify a password against a salted hash."""
    salt = salt_hash[:64].encode("ascii")
    correct_pw_hash = salt_hash[64:]
    computed_pw_hash = hash_password_salt(password, salt).hex()
    return computed_pw_hash == correct_pw_hash
