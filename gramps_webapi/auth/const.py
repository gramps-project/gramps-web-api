"""Constants for the auth module."""

# User roles
ROLE_OWNER = 4
ROLE_EDITOR = 3
ROLE_CONTRIBUTOR = 2
ROLE_MEMBER = 1
ROLE_GUEST = 0

# User permissions
PERM_ADD_USER = "AddUser"
PERM_EDIT_OWN_USER = "EditOwnUser"
PERM_EDIT_OTHER_USER = "EditOtherUser"
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
    ROLE_MEMBER: {PERM_EDIT_OWN_USER, PERM_VIEW_PRIVATE,},
    ROLE_GUEST: {PERM_EDIT_OWN_USER,},
}
