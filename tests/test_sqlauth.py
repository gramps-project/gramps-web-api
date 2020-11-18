#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import unittest

from sqlalchemy.exc import IntegrityError

from gramps_webapi.auth import SQLAuth, User


class TestSQLAuth(unittest.TestCase):
    def test_add_user(self):
        sqlauth = SQLAuth("sqlite://", logging=False)
        sqlauth.create_table()
        with self.assertRaises(IntegrityError):
            sqlauth.add_user(None, "123")  # NULL username
        with self.assertRaises(ValueError):
            sqlauth.add_user("", "123")  # empty username
        with self.assertRaises(ValueError):
            sqlauth.add_user("test_user", "")  # empty pw
        sqlauth.add_user("test_user", "123", fullname="Test User")
        with self.assertRaises(IntegrityError):
            # adding again should fail
            sqlauth.add_user("test_user", "123", fullname="Test User")
        with sqlauth.session_scope() as session:
            user = session.query(User).filter_by(name="test_user").scalar()
            self.assertEqual(user.name, "test_user")
            self.assertEqual(user.fullname, "Test User")

    def test_authorized(self):
        sqlauth = SQLAuth("sqlite://", logging=False)
        sqlauth.create_table()
        sqlauth.add_user("test_user", "123", fullname="Test User")
        self.assertTrue(sqlauth.authorized("test_user", "123"))
        self.assertFalse(sqlauth.authorized("test_user", "1234"))
        self.assertFalse(sqlauth.authorized("not_exist", "123"))

    def test_delete_user(self):
        sqlauth = SQLAuth("sqlite://", logging=False)
        sqlauth.create_table()
        sqlauth.add_user("test_user", "123", fullname="Test User")
        with sqlauth.session_scope() as session:
            user = session.query(User).filter_by(name="test_user").scalar()
            self.assertIsNotNone(user)
            sqlauth.delete_user("test_user")
            user = session.query(User).filter_by(name="test_user").scalar()
            self.assertIsNone(user)
        with self.assertRaisesRegex(ValueError, r".* not found"):
            # deleting again should fail
            sqlauth.delete_user("test_user")

    def test_change_names(self):
        sqlauth = SQLAuth("sqlite://", logging=False)
        sqlauth.create_table()
        sqlauth.add_user("test_user", "123", fullname="Test User")
        guid = sqlauth.get_guid("test_user")
        sqlauth.modify_user("test_user", name_new="test_2", fullname="Test 2")
        with sqlauth.session_scope() as session:
            user = session.query(User).filter_by(id=guid).scalar()
            self.assertEqual(user.name, "test_2")
            self.assertEqual(user.fullname, "Test 2")

    def test_change_pw(self):
        sqlauth = SQLAuth("sqlite://", logging=False)
        sqlauth.create_table()
        sqlauth.add_user("test_user", "123", fullname="Test User")
        sqlauth.modify_user("test_user", password="1234")
        self.assertFalse(sqlauth.authorized("test_user", "123"))
        self.assertTrue(sqlauth.authorized("test_user", "1234"))
        self.assertFalse(sqlauth.authorized("not_exist", "1234"))
