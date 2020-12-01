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

"""Define methods of providing authentication for users."""

import uuid
from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .util.passwords import hash_password, verify_password
from .util.sql_guid import GUID


class AuthProvider(metaclass=ABCMeta):
    """Base class for authentication providers."""

    @abstractmethod
    def authorized(self, username: str, password: str) -> bool:
        """Return true if the username is authorized."""
        return False


Base = declarative_base()


class SQLAuth(AuthProvider):
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

    def get_guid(self, name: str) -> None:
        """Get the GUID of an existing user by username."""
        with self.session_scope() as session:
            user_id = session.query(User.id).filter_by(name=name).scalar()
        return user_id

    def delete_user(self, name: str) -> None:
        """Delete an existing user."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=name).scalar()
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
        """Return true if the username is authorized."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=username).scalar()
            if user is None:
                return False
            return verify_password(password=password, salt_hash=user.pwhash)

    def get_pwhash(self, username: str) -> str:
        """Return the current hashed password."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=username).one()
            return user.pwhash

    def get_user_details(self, username: str) -> Optional[Dict[str, Any]]:
        """Return details about a user."""
        with self.session_scope() as session:
            user = session.query(User).filter_by(name=username).scalar()
            if user is None:
                return None
            return {"id": user.id, "email": user.email, "fullname": user.fullname}


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
        """String representation of instance."""
        return "<User(name='%s', fullname='%s')>" % (self.name, self.fullname)
