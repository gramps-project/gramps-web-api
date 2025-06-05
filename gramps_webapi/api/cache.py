"""Caching functions."""

from __future__ import annotations

import hashlib
import os

from flask import request
from flask_caching import Cache
from gramps.gen.errors import HandleError

from gramps_webapi.api.auth import has_permissions
from gramps_webapi.api.util import (
    abort_with_message,
    get_db_handle,
    get_db_manager,
    get_tree_from_jwt,
    get_tree_from_jwt_or_fail,
)
from gramps_webapi.auth.const import PERM_VIEW_PRIVATE

thumbnail_cache = Cache()
request_cache = Cache()
persistent_cache = Cache()


def get_db_last_change_timestamp(tree_id: str) -> int | float | None:
    """Get the last change timestamp of the database.

    We do this by looking at the modification time of the meta db file.
    If the file does not exist, returns None.
    """
    if not tree_id:
        raise ValueError("Tree ID must not be empty")
    dbmgr = get_db_manager(tree_id)
    meta_path = os.path.join(dbmgr.dbdir, dbmgr.dirname, "meta_data.db")
    try:
        return os.path.getmtime(meta_path)
    except FileNotFoundError:
        return None


def _hash_request_args() -> str:
    """Hash the request arguments for use in cache keys."""
    query_args = list((k, v) for (k, v) in request.args.items(multi=True) if k != "jwt")
    args_as_sorted_tuple = tuple(sorted(query_args))
    args_as_bytes = str(args_as_sorted_tuple).encode()
    arg_hash = hashlib.md5(args_as_bytes)
    return str(arg_hash.hexdigest())


def make_cache_key_thumbnails(*args, **kwargs):
    """Make a cache key for thumbnails."""
    # hash query args except jwt
    arg_hash = _hash_request_args()

    # get media checksum
    handle = kwargs["handle"]
    tree = get_tree_from_jwt()
    db_handle = get_db_handle()
    try:
        obj = db_handle.get_media_from_handle(handle)
    except HandleError:
        abort_with_message(404, f"Handle {handle} not found")
    # checksum in the DB
    checksum = obj.checksum

    dbmgr = get_db_manager(tree)

    cache_key = checksum + request.path + arg_hash + dbmgr.dirname

    return cache_key


def make_cache_key_request(*args, **kwargs):
    """Make a cache key for a base request."""
    # hash query args except jwt
    arg_hash = _hash_request_args()

    # the request result will depend on whether the user can view private records
    # this will be "1" if the user can view private records, "0" otherwise
    permission_hash = str(int(has_permissions({PERM_VIEW_PRIVATE})))

    tree_id = get_tree_from_jwt_or_fail()
    db_timestamp = get_db_last_change_timestamp(tree_id)
    if db_timestamp is None:
        raise ValueError("Database last change timestamp is None")

    cache_key = tree_id + str(db_timestamp) + request.path + arg_hash + permission_hash

    return cache_key


def skip_cache_condition_request(*args, **kwargs) -> bool:
    """Condition to skip caching for a request."""
    # skip caching if the user is not authorized to view private records
    tree_id = get_tree_from_jwt_or_fail()
    db_timestamp = get_db_last_change_timestamp(tree_id)
    # if the database timestamp is None, we cannot determine if the db
    # was changed, so we skip caching!
    should_skip = db_timestamp is None
    return should_skip


request_cache_decorator = request_cache.cached(
    make_cache_key=make_cache_key_request, unless=skip_cache_condition_request
)
thumbnail_cache_decorator = thumbnail_cache.cached(
    make_cache_key=make_cache_key_thumbnails
)
