#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2022      David Straub
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

"""Define methods of providing authentication for users."""

import secrets
import uuid
from typing import Any, Dict, List, Optional, Sequence, Set, Union

import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import mapped_column
from sqlalchemy.sql.functions import coalesce

from ..const import DB_CONFIG_ALLOWED_KEYS
from .const import PERMISSIONS, PERM_USE_CHAT, ROLE_ADMIN, ROLE_OWNER
from .passwords import hash_password, verify_password
from .sql_guid import GUID

user_db = SQLAlchemy()

def add_user(
    name: str,
    password: str,
    fullname: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[int] = None,
    tree: Optional[str] = None,
):
    """Add a user."""
    if name == "":
        raise ValueError("Username must not be empty")
    if password == "":
        raise ValueError("Password must not be empty")
    try:
        user = User(
            id=uuid.uuid4(),
            name=name,
            fullname=fullname,
            email=email,
            pwhash=hash_password(password),
            role=role,
            tree=tree,
        )
        user_db.session.add(user)  # pylint: disable=no-member
        user_db.session.commit()  # pylint: disable=no-member
    except IntegrityError as exc:
        reason = str(exc.orig.args) if exc.orig else ""
        if "name" in reason:
            message = "User already exists"
        elif "email" in reason:
            message = "E-mail already exists"
        else:
            message = "Unexpected database error while trying to add user"
        raise ValueError(message) from exc


def add_users(
    data: List[Dict[str, Union[str, int]]],
    allow_id: bool = False,
    require_password: bool = False,
    allow_admin: bool = False,
):
    """Add multiple users."""
    if not data:
        raise ValueError("No data provided.")
    for user in data:
        if not user.get("name"):
            raise ValueError("Username must not be empty")
        if require_password and not user.get("password"):
            raise ValueError("Password must not be empty")
        if "id" in user and not allow_id:
            raise ValueError("User ID must not be specified")
        if not allow_admin and int(user.get("role", 0)) > ROLE_OWNER:
            raise ValueError("Insufficient permissions to create admin role")
        if "id" not in user:
            user["id"] = str(uuid.uuid4())
        if not user.get("password"):
            # generate random password
            user["password"] = secrets.token_urlsafe(16)
        user["pwhash"] = hash_password(str(user.pop("password")))
        try:
            user_obj = User(**user)
            user_db.session.add(user_obj)  # pylint: disable=no-member
        except IntegrityError as exc:
            raise ValueError("Invalid or existing user") from exc
    user_db.session.commit()  # pylint: disable=no-member


def get_guid(name: str) -> str:
    """Get the GUID of an existing user by username."""
    query = user_db.session.query(User.id)  # pylint: disable=no-member
    user_id = query.filter_by(name=name).scalar()
    if user_id is None:
        raise ValueError(f"User {name} not found")
    return user_id


def get_name(guid: str) -> str:
    """Get the username of an existing user by GUID."""
    try:
        query = user_db.session.query(User.name)  # pylint: disable=no-member
        user_name = query.filter_by(id=guid).scalar()
    except StatementError as exc:
        raise ValueError(f"User ID {guid} not found") from exc
    if user_name is None:
        raise ValueError(f"User ID {guid} not found")
    return user_name


def get_tree(guid: str) -> Optional[str]:
    """Get the tree of an existing user by GUID."""
    try:
        query = user_db.session.query(User.tree)  # pylint: disable=no-member
        tree = query.filter_by(id=guid).scalar()
    except StatementError as exc:
        raise ValueError(f"User ID {guid} not found") from exc
    return tree


def delete_user(name: str) -> None:
    """Delete an existing user."""
    query = user_db.session.query(User)  # pylint: disable=no-member
    user = query.filter_by(name=name).scalar()
    if user is None:
        raise ValueError(f"User {name} not found")
    user_db.session.delete(user)  # pylint: disable=no-member
    user_db.session.commit()  # pylint: disable=no-member


def modify_user(
    name: str,
    name_new: Optional[str] = None,
    password: Optional[str] = None,
    fullname: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[int] = None,
    tree: Optional[str] = None,
) -> None:
    """Modify an existing user."""
    query = user_db.session.query(User)  # pylint: disable=no-member
    user = query.filter_by(name=name).one()
    if name_new is not None:
        user.name = name_new
    if password is not None:
        user.pwhash = hash_password(password)
    if fullname is not None:
        user.fullname = fullname
    if email is not None:
        user.email = email
    if role is not None:
        user.role = role
    if tree is not None:
        user.tree = tree
    user_db.session.commit()  # pylint: disable=no-member


def authorized(username: str, password: str) -> bool:
    """Return true if the user can be authenticated."""
    query = user_db.session.query(User)  # pylint: disable=no-member
    user = query.filter_by(name=username).scalar()
    if user is None:
        return False
    if user.role < 0:
        # users with negative roles cannot login!
        return False
    return verify_password(password=password, salt_hash=user.pwhash)


def get_pwhash(username: str) -> str:
    """Return the current hashed password."""
    query = user_db.session.query(User)  # pylint: disable=no-member
    user = query.filter_by(name=username).one()
    return user.pwhash


def _get_user_detail(user, include_guid: bool = False):
    details = {
        "name": user.name,
        "email": user.email,
        "full_name": user.fullname,
        "role": user.role,
        "tree": user.tree,
    }
    if include_guid:
        details["user_id"] = user.id
    return details


def get_user_details(username: str) -> Optional[Dict[str, Any]]:
    """Return details about a user."""
    query = user_db.session.query(User)  # pylint: disable=no-member
    user = query.filter_by(name=username).scalar()
    if user is None:
        return None
    return _get_user_detail(user)


def get_all_user_details(
    tree: Optional[str], include_treeless=False, include_guid: bool = False
) -> List[Dict[str, Any]]:
    """Return details about all users.

    If tree is None, return all users regardless of tree.
    If tree is not None, only return users of given tree.

    If include_treeless is True, include also users with empty tree ID.
    """
    query = user_db.session.query(User)  # pylint: disable=no-member
    if tree:
        if include_treeless:
            query = query.filter(sa.or_(User.tree == tree, User.tree.is_(None)))
        else:
            query = query.filter(User.tree == tree)
    users = query.all()
    return [_get_user_detail(user, include_guid=include_guid) for user in users]


def get_permissions(username: str, tree: str) -> Set[str]:
    """Get the permissions of a given user."""
    query = user_db.session.query(User)  # pylint: disable=no-member
    user = query.filter_by(name=username).one()
    permissions = PERMISSIONS[user.role].copy()
    # check & add chat permissions
    query = user_db.session.query(Tree)  # pylint: disable=no-member
    tree_obj = query.filter_by(id=tree).scalar()
    if tree_obj and tree_obj.min_role_ai is not None:
        if user.role >= tree_obj.min_role_ai:
            permissions.add(PERM_USE_CHAT)
    return permissions


def get_owner_emails(tree: str, include_admins: bool = False) -> List[str]:
    """Get e-mail addresses of all tree owners (and optionally include site admins)."""
    query = user_db.session.query(User)  # pylint: disable=no-member
    if include_admins:
        users = (
            query.filter_by(tree=tree)
            .filter(sa.or_(User.role == ROLE_OWNER, User.role == ROLE_ADMIN))
            .all()
        )
    else:
        users = query.filter_by(tree=tree, role=ROLE_OWNER).all()
    return [user.email for user in users if user.email]


def get_number_users(
    tree: Optional[str] = None, roles: Optional[Sequence[int]] = None
) -> int:
    """Get the number of users in the database.

    Optionally, provide an iterable of numeric roles and/or a tree ID.
    """
    query = user_db.session.query(User)  # pylint: disable=no-member
    if roles is not None:
        query = query.filter(User.role.in_(roles))
    if tree is not None:
        query = query.filter_by(tree=tree)
    return query.count()


def fill_tree(tree: str) -> None:
    """Fill the tree column with a tree ID, if empty."""
    (
        user_db.session.query(User)  # pylint: disable=no-member
        .filter(coalesce(User.tree, "") == "")  # treat "" and NULL equally
        .update({User.tree: tree}, synchronize_session=False)
    )
    user_db.session.commit()  # pylint: disable=no-member


def config_get(key: str) -> Optional[str]:
    """Get a single config item."""
    query = user_db.session.query(Config)  # pylint: disable=no-member
    config = query.filter_by(key=key).scalar()
    if config is None:
        return None
    return config.value


def config_get_all() -> Dict[str, str]:
    """Get all config items as dictionary."""
    query = user_db.session.query(Config)  # pylint: disable=no-member
    configs = query.all()
    return {c.key: c.value for c in configs}


def config_set(key: str, value: str) -> None:
    """Set a config item."""
    if key not in DB_CONFIG_ALLOWED_KEYS:
        raise ValueError("Config key not allowed.")
    query = user_db.session.query(Config)  # pylint: disable=no-member
    config = query.filter_by(key=key).scalar()
    if config is None:  # does not exist, create
        config = Config(key=str(key), value=str(value))
    else:  # exists, update
        config.value = str(value)
    user_db.session.add(config)  # pylint: disable=no-member
    user_db.session.commit()  # pylint: disable=no-member


def config_delete(key: str) -> None:
    """Delete a config item."""
    query = user_db.session.query(Config)  # pylint: disable=no-member
    config = query.filter_by(key=key).scalar()
    if config is not None:
        user_db.session.delete(config)  # pylint: disable=no-member
        user_db.session.commit()  # pylint: disable=no-member


def get_tree_usage(tree: str) -> Optional[dict[str, int]]:
    """Get tree usage info."""
    query = user_db.session.query(Tree)  # pylint: disable=no-member
    tree_obj: Tree = query.filter_by(id=tree).scalar()
    if tree_obj is None:
        return None
    return {
        "quota_media": tree_obj.quota_media,
        "quota_people": tree_obj.quota_people,
        "quota_ai": tree_obj.quota_ai,
        "usage_media": tree_obj.usage_media,
        "usage_people": tree_obj.usage_people,
        "usage_ai": tree_obj.usage_ai,
    }


def get_tree_permissions(tree: str) -> Optional[dict[str, int]]:
    """Get tree permissions."""
    query = user_db.session.query(Tree)  # pylint: disable=no-member
    tree_obj: Tree = query.filter_by(id=tree).scalar()
    if tree_obj is None:
        return None
    return {"min_role_ai": tree_obj.min_role_ai}


def set_tree_usage(
    tree: str,
    usage_media: Optional[int] = None,
    usage_people: Optional[int] = None,
    usage_ai: Optional[int] = None,
) -> None:
    """Set the tree usage data."""
    if usage_media is None and usage_people is None and usage_ai is None:
        return
    query = user_db.session.query(Tree)  # pylint: disable=no-member
    tree_obj: Tree = query.filter_by(id=tree).scalar()
    if not tree_obj:
        tree_obj = Tree(id=tree)
    if usage_media is not None:
        tree_obj.usage_media = usage_media
    if usage_people is not None:
        tree_obj.usage_people = usage_people
    if usage_ai is not None:
        tree_obj.usage_ai = usage_ai
    user_db.session.add(tree_obj)  # pylint: disable=no-member
    user_db.session.commit()  # pylint: disable=no-member


def set_tree_details(
    tree: str,
    quota_media: Optional[int] = None,
    quota_people: Optional[int] = None,
    min_role_ai: Optional[int] = None,
) -> None:
    """Set the tree details like quotas and minimum role for chat."""
    if quota_media is None and quota_people is None and min_role_ai is None:
        return
    query = user_db.session.query(Tree)  # pylint: disable=no-member
    tree_obj = query.filter_by(id=tree).scalar()
    if not tree_obj:
        tree_obj = Tree(id=tree)
    if quota_media is not None:
        tree_obj.quota_media = quota_media
    if quota_people is not None:
        tree_obj.quota_people = quota_people
    if min_role_ai is not None:
        tree_obj.min_role_ai = min_role_ai
    user_db.session.add(tree_obj)  # pylint: disable=no-member
    user_db.session.commit()  # pylint: disable=no-member


def disable_enable_tree(tree: str, disabled: bool) -> None:
    """Disable or enable a tree."""
    query = user_db.session.query(Tree)  # pylint: disable=no-member
    tree_obj = query.filter_by(id=tree).scalar()
    if not tree_obj:
        tree_obj = Tree(id=tree)
    tree_obj.enabled = 0 if disabled else 1
    user_db.session.add(tree_obj)  # pylint: disable=no-member
    user_db.session.commit()  # pylint: disable=no-member


def is_tree_disabled(tree: str) -> bool:
    """Check if tree is disabled."""
    query = user_db.session.query(Tree)  # pylint: disable=no-member
    tree_obj = query.filter_by(id=tree).scalar()
    if not tree_obj:
        return False
    return tree_obj.enabled == 0


class User(user_db.Model):  # type: ignore
    """User table class for sqlalchemy."""

    __tablename__ = "users"

    id = mapped_column(GUID, primary_key=True)
    name = mapped_column(sa.String, unique=True, nullable=False)
    email = mapped_column(sa.String, unique=True)
    fullname = mapped_column(sa.String)
    pwhash = mapped_column(sa.String, nullable=False)
    role = mapped_column(sa.Integer, default=0)
    tree = mapped_column(sa.String, index=True)

    def __repr__(self):
        """Return string representation of instance."""
        return f"<User(name='{self.name}', fullname='{self.fullname}')>"


class Config(user_db.Model):  # type: ignore
    """Config table class for sqlalchemy."""

    __tablename__ = "configuration"

    id = mapped_column(sa.Integer, primary_key=True)
    key = mapped_column(sa.String, unique=True, nullable=False)
    value = mapped_column(sa.String)

    def __repr__(self):
        """Return string representation of instance."""
        return f"<Config(key='{self.key}', value='{self.value}')>"


class Tree(user_db.Model):  # type: ignore
    """Config table class for sqlalchemy."""

    __tablename__ = "trees"

    id = mapped_column(sa.String, primary_key=True)
    quota_media = mapped_column(sa.BigInteger)
    quota_people = mapped_column(sa.Integer)
    quota_ai = mapped_column(sa.Integer)
    usage_media = mapped_column(sa.BigInteger)
    usage_people = mapped_column(sa.Integer)
    usage_ai = mapped_column(sa.Integer)
    min_role_ai = mapped_column(sa.Integer)
    enabled = mapped_column(sa.Integer, default=1, server_default="1")

    def __repr__(self):
        """Return string representation of instance."""
        return f"<Tree(id='{self.id}')>"
