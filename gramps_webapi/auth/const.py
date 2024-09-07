#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023      David Straub
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

ROLE_ADMIN = 5
ROLE_OWNER = 4
ROLE_EDITOR = 3
ROLE_CONTRIBUTOR = 2
ROLE_MEMBER = 1
ROLE_GUEST = 0
# Roles for unauthorized users
ROLE_DISABLED = -1
ROLE_UNCONFIRMED = -2

# Multi-tree permissions (admin only)
PERM_ADD_OTHER_TREE_USER = "AddOtherTreeUser"
PERM_EDIT_OTHER_TREE_USER = "EditOtherTreeUser"
PERM_EDIT_OTHER_TREE_USER_ROLE = "EditOtherTreeUserRole"
PERM_VIEW_OTHER_TREE_USER = "ViewOtherTreeUser"
PERM_DEL_OTHER_TREE_USER = "DeleteOtherTreeUser"
PERM_EDIT_USER_TREE = "EditUserTree"
PERM_EDIT_OTHER_TREE = "EditOtherTree"
PERM_VIEW_OTHER_TREE = "ViewOtherTree"
PERM_ADD_TREE = "AddTree"
PERM_EDIT_TREE_QUOTA = "EditTreeQuota"
PERM_DISABLE_TREE = "DisableTree"

# User permissions
PERM_ADD_USER = "AddUser"
PERM_EDIT_OWN_USER = "EditOwnUser"
PERM_EDIT_OTHER_USER = "EditOtherUser"
PERM_EDIT_USER_ROLE = "EditUserRole"
PERM_MAKE_ADMIN = "MakeAdmin"
PERM_VIEW_OTHER_USER = "ViewOtherUser"
PERM_DEL_USER = "DeleteUser"
PERM_VIEW_PRIVATE = "ViewPrivate"
PERM_EDIT_OBJ = "EditObject"
PERM_ADD_OBJ = "AddObject"
PERM_DEL_OBJ = "DeleteObject"
PERM_DEL_OBJ_BATCH = "BatchDeleteObjects"
PERM_IMPORT_FILE = "ImportFile"
PERM_VIEW_SETTINGS = "ViewSettings"
PERM_EDIT_SETTINGS = "EditSettings"
PERM_TRIGGER_REINDEX = "TriggerReindex"
PERM_EDIT_NAME_GROUP = "EditNameGroup"
PERM_EDIT_TREE = "EditTree"
PERM_REPAIR_TREE = "RepairTree"
PERM_UPGRADE_TREE_SCHEMA = "UpgradeSchema"
PERM_EDIT_TREE_MIN_ROLE_AI = "EditTreeMinRoleAI"

# permission to use chat
PERM_USE_CHAT = "UseChat"

PERMISSIONS = {}

PERMISSIONS[ROLE_GUEST] = {
    PERM_EDIT_OWN_USER,
}

PERMISSIONS[ROLE_MEMBER] = PERMISSIONS[ROLE_GUEST] | {
    PERM_VIEW_PRIVATE,
}


PERMISSIONS[ROLE_CONTRIBUTOR] = PERMISSIONS[ROLE_MEMBER] | {
    PERM_EDIT_OWN_USER,
    PERM_VIEW_PRIVATE,
    PERM_ADD_OBJ,
}


PERMISSIONS[ROLE_EDITOR] = PERMISSIONS[ROLE_CONTRIBUTOR] | {
    PERM_EDIT_OBJ,
    PERM_DEL_OBJ,
    PERM_EDIT_NAME_GROUP,
}


PERMISSIONS[ROLE_OWNER] = PERMISSIONS[ROLE_EDITOR] | {
    PERM_ADD_USER,
    PERM_DEL_USER,
    PERM_EDIT_OTHER_USER,
    PERM_EDIT_USER_ROLE,
    PERM_VIEW_OTHER_USER,
    PERM_IMPORT_FILE,
    PERM_TRIGGER_REINDEX,
    PERM_EDIT_TREE,
    PERM_REPAIR_TREE,
    PERM_UPGRADE_TREE_SCHEMA,
    PERM_EDIT_TREE_MIN_ROLE_AI,
    PERM_DEL_OBJ_BATCH,
}

PERMISSIONS[ROLE_ADMIN] = PERMISSIONS[ROLE_OWNER] | {
    PERM_ADD_OTHER_TREE_USER,
    PERM_VIEW_OTHER_TREE_USER,
    PERM_EDIT_OTHER_TREE_USER,
    PERM_EDIT_OTHER_TREE_USER_ROLE,
    PERM_EDIT_USER_TREE,
    PERM_MAKE_ADMIN,
    PERM_DEL_OTHER_TREE_USER,
    PERM_VIEW_SETTINGS,
    PERM_EDIT_SETTINGS,
    PERM_VIEW_OTHER_TREE,
    PERM_EDIT_OTHER_TREE,
    PERM_EDIT_TREE_QUOTA,
    PERM_ADD_TREE,
    PERM_DISABLE_TREE,
}

# keys/values for user claims
CLAIM_LIMITED_SCOPE = "limited_scope"
SCOPE_RESET_PW = "reset_password"
SCOPE_CONF_EMAIL = "confirm_email"
SCOPE_CREATE_ADMIN = "create_admin"
SCOPE_CREATE_OWNER = "create_owner"
