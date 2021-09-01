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

"""Define methods of providing authentication for users."""

import uuid
from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Set

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .const import PERMISSIONS, ROLE_OWNER
from .passwords import hash_password, verify_password
from .sql_guid import GUID

Base = declarative_base()


class SQLAuth:
    """SQL Alchemy user database."""

    def __init__(self, db_uri, logging=False):
        """Initialize given a DB URI."""
        self.db_uri = db_uri
        self.engine = sa.create_engine(db_uri, echo=logging)

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        Session = sessionmaker(bind=self.engine)
        session = Session()
        try:
            yield session
            session.commit()  # pylint:disable=no-member
        except:
            session.rollback()  # pylint:disable=no-member
            raise
        finally:
            session.close()  # pylint:disable=no-member

    def create_table(self):
        """Create the user table if it does not exist yet."""
        Base.metadata.create_all(bind=self.engine)

    def add_user(
        self,
        name: str,
        password: str,
        fullname: str = None,
        email: str = None,
        role: int = None,
    ):
        """Add a user."""
        if name == "":
            raise ValueError("Username must not be empty")
        if password == "":
            raise ValueError("Password must not be empty")
        try:
            with self.session_scope() as session:
                user = User(
                    id=uuid.uuid4(),
                    name=name,
                    fullname=fullname,
                    email=email,
                    pwhash=hash_password(password),
                    role=role,
                )
                session.add(user)
        except IntegrityError:
            raise ValueError("Invalid or existing user")

    def get_guid(self, name: str) -> None:
        """Get the GUID of an existing user by username."""
        with self.session_scope() as session:
            user_id = session.query(User.id).filter_by(name=name).scalar()
            if user_id is None:
                raise ValueError("User {} not found".format(name))
        return user_id

    def delete_user(self, name: str) -> None:
        """Delete an existing user."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=name).scalar()
            if user is None:
                raise ValueError("User {} not found".format(name))
            session.delete(user)

    def modify_user(
        self,
        name: str,
        name_new: str = None,
        password: str = None,
        fullname: str = None,
        email: str = None,
        role: int = None,
    ) -> None:
        """Modify an existing user."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=name).one()
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

    def authorized(self, username: str, password: str) -> bool:
        """Return true if the user can be authenticated."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=username).scalar()
            if user is None:
                return False
            if user.role < 0:
                # users with negative roles cannot login!
                return False
            return verify_password(password=password, salt_hash=user.pwhash)

    def get_pwhash(self, username: str) -> str:
        """Return the current hashed password."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=username).one()
            return user.pwhash

    @staticmethod
    def _get_user_detail(user):
        return {
            "name": user.name,
            "email": user.email,
            "full_name": user.fullname,
            "role": user.role,
        }

    def get_user_details(self, username: str) -> Optional[Dict[str, Any]]:
        """Return details about a user."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=username).scalar()
            if user is None:
                return None
            return self._get_user_detail(user)

    def get_all_user_details(self) -> List[Dict[str, Any]]:
        """Return details about all users."""
        with self.session_scope() as session:
            users = session.query(User).all()
            return [self._get_user_detail(user) for user in users]

    def get_permissions(self, username: str) -> Set[str]:
        """Get the permissions of a given user."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=username).one()
            return PERMISSIONS[user.role]

    def get_owner_emails(self) -> List[str]:
        """Get e-mail addresses of all owners."""
        with self.session_scope() as session:
            owners = session.query(User).filter_by(role=ROLE_OWNER).all()
            return [user.email for user in owners if user.email]


class User(Base):
    """User table class for sqlalchemy."""

    __tablename__ = "users"

    id = sa.Column(GUID, primary_key=True)
    name = sa.Column(sa.String, unique=True, nullable=False)
    email = sa.Column(sa.String, unique=True)
    fullname = sa.Column(sa.String)
    pwhash = sa.Column(sa.String, nullable=False)
    role = sa.Column(sa.Integer, default=0)

    def __repr__(self):
        """Return string representation of instance."""
        return "<User(name='%s', fullname='%s')>" % (self.name, self.fullname)
