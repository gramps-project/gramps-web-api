"""Unit tests for `gramps_webapi.util.password`."""

import unittest

from gramps_webapi.util.passwords import hash_password, verify_password


class TestSQLAuth(unittest.TestCase):
    def test_pwhash(self):
        pwhash = hash_password("Xels")
        assert verify_password("Xels", pwhash)
        assert not verify_password("Marmelade", pwhash)
        # again: to check that hash is different
        pwhash2 = hash_password("Xels")
        assert pwhash != pwhash2
        assert verify_password("Xels", pwhash2)
