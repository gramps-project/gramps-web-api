# #
# # Gramps Web API - A RESTful API for the Gramps genealogy program
# #
# # Copyright (C) 2020-2022      David Straub
# #
# # This program is free software; you can redistribute it and/or modify
# # it under the terms of the GNU Affero General Public License as published by
# # the Free Software Foundation; either version 3 of the License, or
# # (at your option) any later version.
# #
# # This program is distributed in the hope that it will be useful,
# # but WITHOUT ANY WARRANTY; without even the implied warranty of
# # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# # GNU Affero General Public License for more details.
# #
# # You should have received a copy of the GNU Affero General Public License
# # along with this program. If not, see <https://www.gnu.org/licenses/>.
# #

# import unittest

# from gramps_webapi.auth import User
# from gramps_webapi.auth.const import (
#     PERM_DEL_USER,
#     PERM_EDIT_OWN_USER,
#     ROLE_OWNER,
#     ROLE_GUEST,
# )


# class TestSQLAuth(unittest.TestCase):
#     def test_add_user(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         with self.assertRaises(ValueError):
#             add_user(None, "123")  # NULL username
#         with self.assertRaises(ValueError):
#             add_user("", "123")  # empty username
#         with self.assertRaises(ValueError):
#             add_user("test_user", "")  # empty pw
#         add_user("test_user", "123", fullname="Test User")
#         with self.assertRaises(ValueError):
#             # adding again should fail
#             add_user("test_user", "123", fullname="Test User")
#         with sqlauth.session_scope() as session:
#             user = session.query(User).filter_by(name="test_user").scalar()
#             self.assertEqual(user.name, "test_user")
#             self.assertEqual(user.fullname, "Test User")

#     def test_authorized(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         add_user("test_user", "123", fullname="Test User")
#         self.assertTrue(sqlauth.authorized("test_user", "123"))
#         self.assertFalse(sqlauth.authorized("test_user", "1234"))
#         self.assertFalse(sqlauth.authorized("not_exist", "123"))

#     def test_delete_user(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         add_user("test_user", "123", fullname="Test User")
#         with sqlauth.session_scope() as session:
#             user = session.query(User).filter_by(name="test_user").scalar()
#             self.assertIsNotNone(user)
#             sqlauth.delete_user("test_user")
#             user = session.query(User).filter_by(name="test_user").scalar()
#             self.assertIsNone(user)
#         with self.assertRaisesRegex(ValueError, r".* not found"):
#             # deleting again should fail
#             sqlauth.delete_user("test_user")

#     def test_change_names(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         add_user("test_user", "123", fullname="Test User")
#         guid = sqlauth.get_guid("test_user")
#         sqlauth.modify_user("test_user", name_new="test_2", fullname="Test 2")
#         with sqlauth.session_scope() as session:
#             user = session.query(User).filter_by(id=guid).scalar()
#             self.assertEqual(user.name, "test_2")
#             self.assertEqual(user.fullname, "Test 2")

#     def test_change_pw(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         add_user("test_user", "123", fullname="Test User")
#         sqlauth.modify_user("test_user", password="1234")
#         self.assertFalse(sqlauth.authorized("test_user", "123"))
#         self.assertTrue(sqlauth.authorized("test_user", "1234"))
#         self.assertFalse(sqlauth.authorized("not_exist", "1234"))

#     def test_permissions(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         add_user("test_owner", "123", role=ROLE_OWNER)
#         add_user("test_guest", "123", role=ROLE_GUEST)
#         self.assertIn(PERM_DEL_USER, sqlauth.get_permissions("test_owner"))
#         self.assertNotIn(PERM_DEL_USER, sqlauth.get_permissions("test_guest"))
#         self.assertIn(PERM_EDIT_OWN_USER, sqlauth.get_permissions("test_owner"))
#         self.assertIn(PERM_EDIT_OWN_USER, sqlauth.get_permissions("test_guest"))

#     def test_count_users(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         assert sqlauth.get_number_users() == 0
#         add_user("user1", "123", role=1)
#         add_user("user2", "123", role=1)
#         add_user("user3", "123", role=3)
#         add_user("user4", "123", role=4)
#         assert sqlauth.get_number_users() == 4
#         assert sqlauth.get_number_users(roles=(1,)) == 2
#         assert sqlauth.get_number_users(roles=(2,)) == 0
#         assert sqlauth.get_number_users(roles=(1, 3)) == 3


# class TestConfig(unittest.TestCase):
#     def test_add_user(self):
#         sqlauth = SQLAuth("sqlite://", logging=False)
#         sqlauth.create_table()
#         assert sqlauth.config_get_all() == {}
#         assert sqlauth.config_get("nope") is None
#         with self.assertRaises(ValueError):
#             sqlauth.config_set("key1", "value1")
#         sqlauth.config_set("EMAIL_HOST", "value1")
#         assert sqlauth.config_get("EMAIL_HOST") == "value1"
#         sqlauth.config_set("EMAIL_HOST", "value2")
#         assert sqlauth.config_get("EMAIL_HOST") == "value2"
#         sqlauth.config_set("EMAIL_HOST", 1)
#         assert sqlauth.config_get("EMAIL_HOST") == "1"
#         sqlauth.config_set("EMAIL_PORT", 2)
#         assert sqlauth.config_get("EMAIL_PORT") == "2"
#         sqlauth.config_delete("EMAIL_HOST")
#         assert sqlauth.config_get("EMAIL_HOST") is None
#         assert sqlauth.config_get("EMAIL_PORT") == "2"
#         assert sqlauth.config_get("nope") is None
#         sqlauth.config_delete("nope")
#         assert sqlauth.config_get("nope") is None
