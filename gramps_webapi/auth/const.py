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

"""Constants for the auth module."""

# User roles
ROLE_OWNER = 4
ROLE_EDITOR = 3
ROLE_CONTRIBUTOR = 2
ROLE_MEMBER = 1
ROLE_GUEST = 0
# Roles for unauthorized users
ROLE_DISABLED = -1
ROLE_UNCONFIRMED = -2

# User permissions
PERM_ADD_USER = "AddUser"
PERM_EDIT_OWN_USER = "EditOwnUser"
PERM_EDIT_OTHER_USER = "EditOtherUser"
PERM_EDIT_USER_ROLE = "EditUserRole"
PERM_VIEW_OTHER_USER = "ViewOtherUser"
PERM_DEL_USER = "DeleteUser"
PERM_VIEW_PRIVATE = "ViewPrivate"
PERM_EDIT_OBJ = "EditObject"
PERM_ADD_OBJ = "AddObject"
PERM_DEL_OBJ = "DeleteObject"

PERMISSIONS = {
    ROLE_OWNER: {
        PERM_ADD_USER,
        PERM_EDIT_OWN_USER,
        PERM_DEL_USER,
        PERM_EDIT_OTHER_USER,
        PERM_EDIT_USER_ROLE,
        PERM_VIEW_OTHER_USER,
        PERM_VIEW_PRIVATE,
        PERM_EDIT_OBJ,
        PERM_ADD_OBJ,
        PERM_DEL_OBJ,
    },
    ROLE_EDITOR: {
        PERM_EDIT_OWN_USER,
        PERM_VIEW_PRIVATE,
        PERM_EDIT_OBJ,
        PERM_ADD_OBJ,
        PERM_DEL_OBJ,
    },
    ROLE_CONTRIBUTOR: {PERM_EDIT_OWN_USER, PERM_VIEW_PRIVATE, PERM_ADD_OBJ,},
    ROLE_MEMBER: {PERM_EDIT_OWN_USER, PERM_VIEW_PRIVATE,},
    ROLE_GUEST: {PERM_EDIT_OWN_USER,},
}

# keys/values for user claims
CLAIM_LIMITED_SCOPE = "limited_scope"
SCOPE_RESET_PW = "reset_password"
SCOPE_CONF_EMAIL = "confirm_email"
