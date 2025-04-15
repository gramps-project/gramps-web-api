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

"""User administration resources."""

import datetime
from gettext import gettext as _
from typing import Optional, Tuple

from flask import abort, current_app, jsonify, render_template, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity
from webargs import fields

from ...auth import (
    add_user,
    add_users,
    authorized,
    delete_user,
    get_all_user_details,
    get_guid,
    get_name,
    get_number_users,
    get_pwhash,
    get_user_details,
    modify_user,
)
from ...auth.const import (
    CLAIM_LIMITED_SCOPE,
    PERM_ADD_OTHER_TREE_USER,
    PERM_ADD_USER,
    PERM_DEL_OTHER_TREE_USER,
    PERM_DEL_USER,
    PERM_EDIT_OTHER_TREE_USER,
    PERM_EDIT_OTHER_TREE_USER_ROLE,
    PERM_EDIT_OTHER_USER,
    PERM_EDIT_OWN_USER,
    PERM_EDIT_USER_ROLE,
    PERM_EDIT_USER_TREE,
    PERM_MAKE_ADMIN,
    PERM_VIEW_OTHER_TREE_USER,
    PERM_VIEW_OTHER_USER,
    ROLE_ADMIN,
    ROLE_DISABLED,
    ROLE_OWNER,
    ROLE_UNCONFIRMED,
    SCOPE_CONF_EMAIL,
    SCOPE_CREATE_ADMIN,
    SCOPE_CREATE_OWNER,
    SCOPE_RESET_PW,
)
from ...const import TREE_MULTI
from ..auth import has_permissions, require_permissions
from ..ratelimiter import limiter
from ..tasks import (
    AsyncResult,
    make_task_response,
    run_task,
    send_email_confirm_email,
    send_email_new_user,
    send_email_reset_password,
)
from ..util import (
    abort_with_message,
    get_tree_from_jwt,
    get_tree_id,
    tree_exists,
    use_args,
)
from . import LimitedScopeProtectedResource, ProtectedResource, Resource


class UserChangeBase(ProtectedResource):
    """Base class for user change endpoints."""

    def prepare_edit(self, user_name: str) -> Tuple[str, bool]:
        """Cheks to do before processing the request."""
        if user_name == "-":
            require_permissions([PERM_EDIT_OWN_USER])
            user_id = get_jwt_identity()
            try:
                user_name = get_name(user_id)
            except ValueError:
                abort_with_message(401, "User not found for token ID")
            other_tree = False
        else:
            try:
                user_id = get_guid(user_name)
            except ValueError:
                abort_with_message(404, "User with this name does not exist")
            source_tree = get_tree_from_jwt()
            destination_tree = get_tree_id(user_id)
            if source_tree == destination_tree:
                require_permissions([PERM_EDIT_OTHER_USER])
                other_tree = False
            else:
                require_permissions([PERM_EDIT_OTHER_TREE_USER])
                other_tree = True
        return user_name, other_tree


class UsersResource(ProtectedResource):
    """Resource for all users."""

    def get(self):
        """Get users' details."""
        if has_permissions([PERM_VIEW_OTHER_TREE_USER]):
            # return all users from all trees
            return jsonify(get_all_user_details(tree=None)), 200
        require_permissions([PERM_VIEW_OTHER_USER])
        tree = get_tree_from_jwt()
        # return only this tree's users
        # only include treeless users in single-tree setup
        is_single = current_app.config["TREE"] != TREE_MULTI
        details = get_all_user_details(tree=tree, include_treeless=is_single)
        return (
            jsonify(details),
            200,
        )

    def post(self):
        """Add one or more users."""
        users = request.json
        if not users:
            abort_with_message(422, "Empty payload")
        require_permissions([PERM_ADD_USER])
        tree = get_tree_from_jwt()
        for user_dict in users:
            if user_dict.get("tree"):
                if not tree_exists(user_dict["tree"]):
                    abort_with_message(422, "Tree does not exist")
                if user_dict["tree"] != tree:
                    require_permissions([PERM_ADD_OTHER_TREE_USER])
            else:
                user_dict["tree"] = tree
        users = [
            {
                "name": user_dict.get("name"),
                "email": user_dict.get("email"),
                # user correct argument name for full name
                "fullname": user_dict.get("full_name"),
                "role": user_dict.get("role", 0),
                "tree": user_dict.get("tree"),
            }
            for user_dict in users
        ]
        try:
            add_users(
                users,
                allow_id=False,
                require_password=False,
                allow_admin=has_permissions([PERM_MAKE_ADMIN]),
            )
        except ValueError as exc:
            abort_with_message(409, str(exc))
        return "", 201


class UserResource(UserChangeBase):
    """Resource for a single user."""

    def get(self, user_name: str):
        """Get a user's details."""
        if user_name == "-":
            # own user
            user_id = get_jwt_identity()
            try:
                user_name = get_name(user_id)
            except ValueError:
                abort_with_message(401, "User not found for token ID")
        else:
            require_permissions([PERM_VIEW_OTHER_USER])
        if user_name != "_" and not has_permissions([PERM_VIEW_OTHER_TREE_USER]):
            # check if this is our tree
            try:
                user_id = get_guid(user_name)
            except ValueError:
                abort_with_message(404, "User with this name does not exist")
            source_tree = get_tree_from_jwt()
            destination_tree = get_tree_id(user_id)
            if source_tree != destination_tree:
                # user lives in other tree, not allowed to view
                abort_with_message(403, "Not authorized to view other users' details")
        details = get_user_details(user_name)
        if details is None:
            # user does not exist
            abort_with_message(404, "User does not exist")
        return jsonify(details), 200

    @use_args(
        {
            "email": fields.Str(required=False),
            "full_name": fields.Str(required=False),
            "role": fields.Int(required=False),
            "tree": fields.Str(required=False),
        },
        location="json",
    )
    def put(self, args, user_name: str):
        """Update a user's details."""
        user_name, other_tree = self.prepare_edit(user_name)
        if "role" in args:
            if args["role"] >= ROLE_ADMIN:
                # only admins can elevate users to admins
                require_permissions([PERM_MAKE_ADMIN])
            if other_tree:
                require_permissions([PERM_EDIT_OTHER_TREE_USER_ROLE])
            else:
                require_permissions([PERM_EDIT_USER_ROLE])
        if "tree" in args:
            require_permissions([PERM_EDIT_USER_TREE])
            if not tree_exists(args["tree"]):
                abort_with_message(422, "Tree does not exist")
        modify_user(
            name=user_name,
            email=args.get("email"),
            fullname=args.get("full_name"),
            role=args.get("role"),
            tree=args.get("tree"),
        )
        return "", 200

    @use_args(
        {
            "email": fields.Str(required=True),
            "full_name": fields.Str(required=True),
            "password": fields.Str(required=True),
            "role": fields.Int(required=True),
            "tree": fields.Str(required=False),
        },
        location="json",
    )
    def post(self, args, user_name: str):
        """Add a new user."""
        if user_name == "-":
            # Adding a new user does not make sense for "own" user
            abort(404)
        if args["role"] >= ROLE_ADMIN:
            # only admins can create new admin users
            require_permissions([PERM_MAKE_ADMIN])
        tree = get_tree_from_jwt()
        if not args.get("tree") or tree == args.get("tree"):
            require_permissions([PERM_ADD_USER])
        else:
            require_permissions([PERM_ADD_OTHER_TREE_USER])
            if not tree_exists(args["tree"]):
                abort_with_message(422, "Tree does not exist")
        try:
            add_user(
                name=user_name,
                password=args["password"],
                email=args["email"],
                fullname=args["full_name"],
                role=args["role"],
                # use posting user's tree unless explicitly specified
                tree=args.get("tree") or tree,
            )
        except ValueError as exc:
            abort_with_message(409, str(exc))
        return "", 201

    def delete(self, user_name: str):
        """Delete a user."""
        if user_name == "-":
            # Deleting the own user is currently not allowed
            abort(404)
        try:
            user_id = get_guid(name=user_name)
        except ValueError:
            abort(404)  # user not found
        source_tree = get_tree_from_jwt()
        destination_tree = get_tree_id(user_id)
        if source_tree == destination_tree:
            require_permissions([PERM_DEL_USER])
        else:
            require_permissions([PERM_DEL_OTHER_TREE_USER])
        delete_user(name=user_name)
        return "", 200


class UserRegisterResource(Resource):
    """Resource for registering a new user."""

    def _is_disabled(self, tree: Optional[str]) -> bool:
        """Check if the registration is disabled."""
        if current_app.config["REGISTRATION_DISABLED"]:
            return True
        # check if there are tree owners or, in a single-tree setup,
        # tree admins
        if current_app.config["TREE"] == TREE_MULTI:
            roles = [ROLE_OWNER]
        else:
            roles = [ROLE_OWNER, ROLE_ADMIN]
        if get_number_users(tree=tree, roles=roles) == 0:
            # no users authorized to enable new accounts:
            # registration disabled
            return True
        return False

    @limiter.limit("1/second")
    @use_args(
        {
            "email": fields.Str(required=True),
            "full_name": fields.Str(required=True),
            "password": fields.Str(required=True),
            "tree": fields.Str(required=False),
        },
        location="json",
    )
    def post(self, args, user_name: str):
        """Register a new user."""
        if user_name == "-":
            # Registering a new user does not make sense for "own" user
            abort(404)
        if not args.get("tree") and current_app.config["TREE"] == TREE_MULTI:
            # if multi-tree is enabled, tree is required
            abort_with_message(422, "tree is required")
        # do not allow registration if no tree owner account exists!
        if self._is_disabled(tree=args.get("tree")):
            abort_with_message(405, "Registration is disabled")
        if (
            "tree" in args
            and current_app.config["TREE"] != TREE_MULTI
            and args["tree"] != current_app.config["TREE"]
        ):
            abort_with_message(422, "Not allowed in single-tree setup")
        if "tree" in args and not tree_exists(args["tree"]):
            abort_with_message(422, "Tree does not exist")
        try:
            add_user(
                name=user_name,
                password=args["password"],
                email=args["email"],
                fullname=args["full_name"],
                tree=args.get("tree"),
                role=ROLE_UNCONFIRMED,
            )
        except ValueError as exc:
            abort_with_message(409, str(exc))
        user_id = get_guid(name=user_name)
        token = create_access_token(
            identity=str(user_id),
            additional_claims={
                "email": args["email"],
                CLAIM_LIMITED_SCOPE: SCOPE_CONF_EMAIL,
            },
            # link does not expire
            expires_delta=False,
        )
        run_task(
            send_email_confirm_email,
            email=args["email"],
            user_name=user_name,
            token=token,
        )
        return "", 201


class UserCreateOwnerResource(LimitedScopeProtectedResource):
    """Resource for creating a site admin when the user database is empty."""

    @limiter.limit("1/second")
    @use_args(
        {
            "email": fields.Str(required=True),
            "full_name": fields.Str(required=True),
            "password": fields.Str(required=True),
            "tree": fields.Str(required=False),
        },
        location="json",
    )
    def post(self, args, user_name: str):
        """Create a user with admin permissions."""
        if user_name == "-":
            # User name - is not allowed
            abort(404)
        claims = get_jwt()
        if "tree" in args and not tree_exists(args["tree"]):
            abort_with_message(422, "Tree does not exist")
        if (
            "tree" in args
            and current_app.config["TREE"] != TREE_MULTI
            and args["tree"] != current_app.config["TREE"]
        ):
            abort_with_message(422, "Not allowed in single-tree setup")
        if claims[CLAIM_LIMITED_SCOPE] == SCOPE_CREATE_ADMIN:
            if get_number_users() > 0:
                # there is already a user in the user DB
                abort_with_message(405, "Users already exist")
            add_user(
                name=user_name,
                password=args["password"],
                email=args["email"],
                fullname=args["full_name"],
                tree=args.get("tree"),
                role=ROLE_ADMIN,
            )
        elif claims[CLAIM_LIMITED_SCOPE] == SCOPE_CREATE_OWNER:
            tree = claims["tree"]
            if "tree" in args and args["tree"] != tree:
                abort_with_message(422, "Not allowed for this tree")
            if not tree_exists(tree_id=tree):
                abort_with_message(422, "Tree does not exist")
            if get_number_users(tree=tree) > 0:
                abort_with_message(405, "Users already exist")
            try:
                add_user(
                    name=user_name,
                    password=args["password"],
                    email=args["email"],
                    fullname=args["full_name"],
                    tree=tree,
                    role=ROLE_OWNER,
                )
            except ValueError as exc:
                abort_with_message(409, str(exc))

        else:
            abort_with_message(403, "Wrong token")
        return "", 201


class UserChangePasswordResource(UserChangeBase):
    """Resource for changing a user password."""

    @use_args(
        {
            "old_password": fields.Str(required=True),
            "new_password": fields.Str(required=True),
        },
        location="json",
    )
    def post(self, args, user_name: str):
        """Post new password."""
        user_name, _ = self.prepare_edit(user_name)
        if len(args["new_password"]) == "":
            abort_with_message(400, "Empty password provided")
        if not authorized(user_name, args["old_password"]):
            abort_with_message(403, "Old password incorrect")
        modify_user(name=user_name, password=args["new_password"])
        return "", 201


class UserTriggerResetPasswordResource(Resource):
    """Resource for obtaining a one-time JWT for password reset."""

    @limiter.limit("1/second")
    def post(self, user_name):
        """Post username to initiate the password reset."""
        if user_name == "-":
            # password reset trigger not make sense for "own" user since not logged in
            abort(404)
        details = get_user_details(user_name)
        if details is None:
            # user does not exist!
            abort(404)
        email = details["email"]
        if email is None:
            abort(404)
        user_id = get_guid(name=user_name)
        token = create_access_token(
            identity=str(user_id),
            # the hash of the existing password is stored in the token in order
            # to make sure the rest token can only be used once
            additional_claims={
                "old_hash": get_pwhash(user_name),
                CLAIM_LIMITED_SCOPE: SCOPE_RESET_PW,
            },
            # password reset has to be triggered within 1h
            expires_delta=datetime.timedelta(hours=1),
        )
        try:
            task = run_task(
                send_email_reset_password, email=email, user_name=user_name, token=token
            )
        except ValueError:
            abort_with_message(500, "Error while trying to send e-mail")
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return "", 201


class UserResetPasswordResource(LimitedScopeProtectedResource):
    """Resource for resetting a user password."""

    @use_args(
        {"new_password": fields.Str(required=True)},
        location="json",
    )
    def post(self, args):
        """Post new password."""
        if args["new_password"] == "":
            abort_with_message(400, "Empty password provided")
        claims = get_jwt()
        if claims[CLAIM_LIMITED_SCOPE] != SCOPE_RESET_PW:
            # This is a wrong token!
            abort_with_message(403, "Wrong token")
        user_id = get_jwt_identity()
        try:
            username = get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
        # the old PW hash is stored in the reset JWT to check if the token has
        # been used already
        if claims["old_hash"] != get_pwhash(username):
            # the one-time token has been used before!
            abort_with_message(409, "This token can only be used once")
        modify_user(name=username, password=args["new_password"])
        return "", 201

    def get(self):
        """Reset password form."""
        user_id = get_jwt_identity()
        try:
            username = get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
        claims = get_jwt()
        if claims[CLAIM_LIMITED_SCOPE] != SCOPE_RESET_PW:
            # This is a wrong token!
            abort_with_message(403, "Wrong token")
        # the old PW hash is stored in the reset JWT to check if the token has
        # been used already
        if claims["old_hash"] != get_pwhash(username):
            # the one-time token has been used before!
            return render_template("reset_password_error.html", username=username)
        return render_template("reset_password.html", username=username)


class UserConfirmEmailResource(LimitedScopeProtectedResource):
    """Resource for confirming an email address."""

    def get(self):
        """Show email confirmation dialog."""
        user_id = get_jwt_identity()
        try:
            username = get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
        claims = get_jwt()
        if claims[CLAIM_LIMITED_SCOPE] != SCOPE_CONF_EMAIL:
            # This is a wrong token!
            abort_with_message(403, "Wrong token")
        current_details = get_user_details(username)
        assert current_details is not None  # for type checker
        # the email is stored in the JWT
        if claims["email"] != current_details.get("email"):
            # This is a wrong token!
            abort_with_message(403, "Wrong token")
        if current_details["role"] == ROLE_UNCONFIRMED:
            # otherwise it has been confirmed already
            modify_user(name=username, role=ROLE_DISABLED)
            # we cannot use get_tree_from_jwt here since the JWT does not
            # contain the tree ID
            tree = get_tree_id(user_id)
            is_multi = current_app.config["TREE"] == TREE_MULTI
            run_task(
                send_email_new_user,
                username=username,
                fullname=current_details.get("full_name", ""),
                email=claims["email"],
                tree=tree,
                # for single-tree setups, send e-mail also to admins
                include_admins=not is_multi,
            )
        title = _("E-mail address confirmation")
        message = _(
            "Thank you for confirming your e-mail address. "
            "An administrator will review your account request."
        )
        return render_template("confirmation.html", title=title, message=message)
