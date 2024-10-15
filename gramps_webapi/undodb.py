#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2024       David Straub
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


"""SQLite database with undo history."""

import json
import pickle
from contextlib import contextmanager
from time import time_ns
from typing import Any, Dict, List, Optional, Tuple

import gramps
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import REFERENCE_KEY, TXNADD, TXNDEL, TXNUPD, DbUndo, DbWriteBase
from gramps.gen.db.dbconst import CLASS_TO_KEY_MAP, KEY_TO_CLASS_MAP, KEY_TO_NAME_MAP
from gramps.gen.db.txn import DbTxn
from gramps.gen.lib.serialize import to_json
from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    create_engine,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

_ = glocale.translation.gettext

Base = declarative_base()


class Change(Base):
    """A change is a single addition, deletion, or modification of a Gramps object."""

    __tablename__ = "changes"
    __table_args__ = (PrimaryKeyConstraint("id", "connection_id"),)

    id = Column(Integer)
    connection_id = Column(Integer, ForeignKey("connections.id"), index=True)
    obj_class = Column(Text)
    trans_type = Column(Integer)
    obj_handle = Column(Text)
    ref_handle = Column(Text)
    old_data = Column(LargeBinary)
    new_data = Column(LargeBinary)
    timestamp = Column(BigInteger, index=True)

    connection = relationship("Connection", back_populates="changes")

    def _obj_to_json(self, data):
        """Convert binary object to a JSON dict."""
        if data is None:
            return {}
        try:
            obj_cls = getattr(gramps.gen.lib, self.obj_class)
        except AttributeError:
            return {}
        serial_data = pickle.loads(data)
        obj = obj_cls().unserialize(serial_data)
        json_string = to_json(obj)
        return json.loads(json_string)

    def _to_dict(self, old_data: bool = True, new_data: bool = True):
        """Return a dict representation of the change."""

        data = {
            "id": self.id,
            "obj_class": self.obj_class,
            "trans_type": self.trans_type,
            "obj_handle": self.obj_handle,
            "ref_handle": self.ref_handle,
            "timestamp": self.timestamp / 1e9,
        }
        if old_data:
            old = self._obj_to_json(self.old_data)
            data["old_data"] = old
        if new_data:
            new = self._obj_to_json(self.new_data)
            data["new_data"] = new
        return data


class Connection(Base):
    """A connection is a bunch of database transactions grouped together.

    In Gramps desktop, it will typically correspond to a session between opening and
    closing the app. In Gramps Web API, it will correspond to HTTP requests.
    """

    __tablename__ = "connections"

    id = Column(Integer, primary_key=True)
    tree_id = Column(Integer, index=True)
    user_id = Column(Text, index=True)
    timestamp = Column(BigInteger, index=True)

    changes = relationship("Change", back_populates="connection")
    transactions = relationship("Transaction", back_populates="connection")

    def _to_dict(self):
        """Return a dict representation of the connection."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "timestamp": self.timestamp / 1e9,
        }


class Transaction(Base):
    """A transaction corresponds to a Gramps database transaction.

    It consists of one or more changes.
    """

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("connections.id"), index=True)
    description = Column(Text)
    first = Column(Integer)
    last = Column(Integer)
    undo = Column(Integer)
    timestamp = Column(BigInteger, index=True)

    connection = relationship("Connection", back_populates="transactions")

    def _to_dict(self, old_data: bool = True, new_data: bool = True):
        """Return a dict representation of the transaction."""
        return {
            "id": self.id,
            "connection": self.connection._to_dict(),
            "description": self.description,
            "first": self.first,
            "last": self.last,
            "undo": bool(self.undo),
            "timestamp": self.timestamp / 1e9,
            "changes": [
                change._to_dict(old_data=old_data, new_data=new_data)
                for change in self.connection.changes
            ],
        }


class DbUndoSQL(DbUndo):
    """SQL-based undo database."""

    def __init__(
        self,
        grampsdb: DbWriteBase,
        dburl: str,
        tree_id: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> None:
        DbUndo.__init__(self, grampsdb)
        self._connection_id: Optional[int] = None
        self.tree_id = tree_id
        self.user_id = user_id
        self.undodb: List[bytes] = []
        self.engine = create_engine(dburl)

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        SQLSession = sessionmaker(self.engine)
        session = SQLSession()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

    @property
    def connection_id(self) -> int:
        """Return the cached connection ID or create if not exists."""
        if self._connection_id is None:
            self._connection_id = self._make_connection_id()
        return self._connection_id

    def open(self, value=None) -> None:
        """
        Open the backing storage.
        """
        try:
            Base.metadata.create_all(self.engine)
        except OperationalError as e:
            if "already exists" not in str(e):
                raise

    def _make_connection_id(self) -> int:
        """Insert a row into the connection table."""
        with self.session_scope() as session:
            new_connection = Connection(
                timestamp=time_ns(), tree_id=self.tree_id, user_id=self.user_id
            )
            session.add(new_connection)
            session.commit()
            return new_connection.id

    def close(self) -> None:
        """Close the backing storage."""
        self.engine.dispose()

    def append(self, value) -> None:
        """Add a new entry on the end."""
        (obj_type, trans_type, handle, old_data, new_data) = pickle.loads(value)
        if isinstance(handle, tuple):
            obj_handle, ref_handle = handle
        else:
            obj_handle, ref_handle = (handle, None)
        length = len(self)
        connection_id = self.connection_id  # outside session to prevent lock error
        with self.session_scope() as session:
            old_data = None if old_data is None else pickle.dumps(old_data, protocol=1)
            new_data = None if new_data is None else pickle.dumps(new_data, protocol=1)
            new_change = Change(
                connection_id=connection_id,
                id=length + 1,
                obj_class=KEY_TO_CLASS_MAP.get(obj_type, str(obj_type)),
                trans_type=trans_type,
                obj_handle=obj_handle,
                ref_handle=ref_handle,
                old_data=old_data,
                new_data=new_data,
                timestamp=time_ns(),
            )
            session.add(new_change)
            session.commit()

    def _after_commit(
        self, transaction: DbTxn, undo: bool = False, redo: bool = False
    ) -> None:
        """Post-transaction commit processing."""
        msg = transaction.get_description()
        if redo:
            msg = _("_Redo %s") % msg
        if undo:
            msg = _("_Undo %s") % msg
        if undo or redo:
            timestamp = time_ns()  # update timestamp to now
        else:
            timestamp = int(transaction.timestamp * 1e9)  # integer nanoseconds
        if transaction.first is None:
            first = None
        else:
            first = transaction.first + 1  # Python index vs SQL id off-by-1
        if transaction.last is None:
            last = None
        else:
            last = transaction.last + 1
        connection_id = self.connection_id  # outside session to prevent lock error
        with self.session_scope() as session:
            new_transaction = Transaction(
                connection_id=connection_id,
                description=msg,
                timestamp=timestamp,
                first=first,
                last=last,
                undo=int(undo),
            )
        session.add(new_transaction)
        session.commit()

    def __getitem__(self, index: int) -> bytes:
        """
        Returns an entry by index number.
        """
        connection_id = self.connection_id  # outside session to prevent lock error
        with self.session_scope() as session:
            change = (
                session.query(Change)
                .filter(Change.connection_id == connection_id, Change.id == index + 1)
                .first()
            )

            if change is None:
                raise IndexError("list index out of range")

            obj_class = int(CLASS_TO_KEY_MAP.get(change.obj_class, change.obj_class))
            old_data = (
                None if change.old_data is None else pickle.loads(change.old_data)
            )
            new_data = (
                None if change.new_data is None else pickle.loads(change.new_data)
            )

            if change.ref_handle:
                handle = (change.obj_handle, change.ref_handle)
            else:
                handle = change.obj_handle

            blob_data = pickle.dumps(
                (obj_class, change.trans_type, handle, old_data, new_data),
                protocol=1,
            )
            return blob_data

    def __setitem__(self, index: int, value: bytes) -> None:
        """
        Set an entry to a value.
        """
        (obj_type, trans_type, handle, old_data, new_data) = pickle.loads(value)
        if isinstance(handle, tuple):
            obj_handle, ref_handle = handle
        else:
            obj_handle, ref_handle = (handle, None)
        connection_id = self.connection_id  # outside session to prevent lock error
        with self.session_scope() as session:
            change = (
                session.query(Change)
                .filter(Change.connection_id == connection_id, Change.id == index + 1)
                .first()
            )

            if change is None:
                raise IndexError("list index out of range")

            change.obj_class = KEY_TO_CLASS_MAP.get(obj_type, str(obj_type))
            change.trans_type = trans_type
            change.obj_handle = obj_handle
            change.ref_handle = ref_handle
            change.old_data = (
                pickle.dumps(old_data, protocol=1) if old_data is not None else None
            )
            change.new_data = (
                pickle.dumps(new_data, protocol=1) if new_data is not None else None
            )
            change.timestamp = time_ns()

            session.commit()

    def __len__(self) -> int:
        """Returns the number of entries."""
        connection_id = self.connection_id  # outside session to prevent lock error
        with self.session_scope() as session:
            max_id = (
                session.query(func.max(Change.id))
                .filter(Change.connection_id == connection_id)
                .scalar()
            )
        return max_id or 0

    def _redo(self, update_history: bool) -> bool:
        """
        Access the last undone transaction, and revert the data to the state
        before the transaction was undone.
        """
        txn = self.redoq.pop()
        self.undoq.append(txn)
        transaction = txn
        db = self.db
        subitems = transaction.get_recnos()
        # sigs[obj_type][trans_type]
        sigs = [[[] for trans_type in range(3)] for key in range(11)]
        records = {record_id: self[record_id] for record_id in subitems}

        # Process all records in the transaction
        try:
            self.db._txn_begin()
            for record_id in subitems:
                (key, trans_type, handle, old_data, new_data) = pickle.loads(
                    records[record_id]
                )

                if key == REFERENCE_KEY:
                    self.db.undo_reference(new_data, handle)
                else:
                    self.db.undo_data(new_data, handle, key)
                    sigs[key][trans_type].append(handle)
            # now emit the signals
            self.undo_sigs(sigs, False)

            self.db._txn_commit()
        except:
            self.db._txn_abort()
            raise

        # Notify listeners
        if db.undo_callback:
            db.undo_callback(_("_Undo %s") % transaction.get_description())

        if db.redo_callback:
            if self.redo_count > 1:
                new_transaction = self.redoq[-2]
                db.redo_callback(_("_Redo %s") % new_transaction.get_description())
            else:
                db.redo_callback(None)

        if update_history and db.undo_history_callback:
            db.undo_history_callback()

        self._after_commit(transaction, undo=False, redo=True)

        return True

    def _undo(self, update_history: bool) -> bool:
        """
        Access the last committed transaction, and revert the data to the
        state before the transaction was committed.
        """
        txn = self.undoq.pop()
        self.redoq.append(txn)
        transaction = txn
        db = self.db
        subitems = transaction.get_recnos(reverse=True)
        # sigs[obj_type][trans_type]
        sigs = [[[] for trans_type in range(3)] for key in range(11)]
        records = {record_id: self[record_id] for record_id in subitems}

        # Process all records in the transaction
        try:
            self.db._txn_begin()
            for record_id in subitems:
                (key, trans_type, handle, old_data, new_data) = pickle.loads(
                    records[record_id]
                )

                if key == REFERENCE_KEY:
                    self.db.undo_reference(old_data, handle)
                else:
                    self.db.undo_data(old_data, handle, key)
                    sigs[key][trans_type].append(handle)
            # now emit the signals
            self.undo_sigs(sigs, True)

            self.db._txn_commit()
        except:
            self.db._txn_abort()
            raise

        # Notify listeners
        if db.undo_callback:
            if self.undo_count > 0:
                db.undo_callback(_("_Undo %s") % self.undoq[-1].get_description())
            else:
                db.undo_callback(None)

        if db.redo_callback:
            db.redo_callback(_("_Redo %s") % transaction.get_description())

        if update_history and db.undo_history_callback:
            db.undo_history_callback()

        self._after_commit(transaction, undo=True, redo=False)

        return True

    def undo_sigs(self, sigs, undo):
        """
        Helper method to undo/redo the signals for changes made
        We want to do deletes and adds first
        Note that if 'undo' we swap emits
        """
        for trans_type in [TXNDEL, TXNADD, TXNUPD]:
            for obj_type in range(11):
                handles = sigs[obj_type][trans_type]
                if handles:
                    if (
                        not undo
                        and trans_type == TXNDEL
                        or undo
                        and trans_type == TXNADD
                    ):
                        typ = "-delete"
                    else:
                        # don't update a handle if its been deleted, and note
                        # that 'deleted' handles are in the 'add' list if we
                        # are undoing
                        handles = [
                            handle
                            for handle in handles
                            if handle not in sigs[obj_type][TXNADD if undo else TXNDEL]
                        ]
                        if ((not undo) and trans_type == TXNADD) or (
                            undo and trans_type == TXNDEL
                        ):
                            typ = "-add"
                        else:  # TXNUPD
                            typ = "-update"
                    if handles:
                        self.db.emit(KEY_TO_NAME_MAP[obj_type] + typ, (handles,))


class DbUndoSQLWeb(DbUndoSQL):
    """SQL-based undo database with additional methods for Web API."""

    def get_transactions(
        self,
        page: int = 1,
        pagesize: int = 20,
        old_data: bool = True,
        new_data: bool = True,
        ascending: bool = True,
        before: Optional[int] = None,
        after: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get transactions as a JSONifiable list."""
        with self.session_scope() as session:
            query = (
                session.query(Transaction)
                .outerjoin(Connection)
                .outerjoin(Change)
                .filter(Connection.tree_id == self.tree_id)
                .filter((Change.id >= Transaction.first) | Transaction.first.is_(None))
                .filter((Change.id <= Transaction.last) | Transaction.first.is_(None))
                .group_by(Transaction.id)
            )
            if before:
                query = query.filter(Transaction.timestamp < before * 1e9)
            if after:
                query = query.filter(Transaction.timestamp > after * 1e9)
            count = query.count()
            if ascending:
                query = query.order_by(Transaction.id)
            else:
                query = query.order_by(Transaction.id.desc())
            if page and pagesize:
                query = query.limit(pagesize).offset((page - 1) * pagesize)
            transactions = query.all()
            return [
                transaction._to_dict(old_data=old_data, new_data=new_data)
                for transaction in transactions
            ], count

    def get_transaction(
        self,
        transaction_id: int,
        old_data: bool = True,
        new_data: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get a single transaction as a JSONifiable dict."""
        with self.session_scope() as session:
            query = (
                session.query(Transaction)
                .outerjoin(Connection)
                .outerjoin(Change)
                .filter(Connection.tree_id == self.tree_id)
                .filter(Transaction.id == transaction_id)
                .filter((Change.id >= Transaction.first) | Transaction.first.is_(None))
                .filter((Change.id <= Transaction.last) | Transaction.first.is_(None))
            )
            transaction = query.scalar()
            return transaction._to_dict(old_data=old_data, new_data=new_data)
