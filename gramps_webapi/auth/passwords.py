#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Password utility functions."""

import hashlib
import os
from secrets import compare_digest


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
    return compare_digest(computed_pw_hash, correct_pw_hash)
