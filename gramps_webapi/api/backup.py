#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Create and read backup archives of a tree.

A backup archive is an uncompressed tar file containing a manifest
(`backup.json`), the tree's data as Gramps XML (`data.gramps`), its settings
(`tree.json`), its users without credentials (`users.json`) and a list of its
media files (`media.json`). The media files themselves are not included.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flask import current_app
from gramps.gen.const import ENV
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.generic import DbGeneric
from gramps.gen.lib import Media
from gramps.gen.plug import BasePluginManager
from gramps.gen.user import User, UserBase

from ..auth import (
    add_user,
    get_all_user_details,
    get_guid,
    get_tree_config,
    set_tree_config,
)
from ..auth.const import PERMISSIONS, ROLE_OWNER
from ..const import GRAMPS_OBJECT_PLURAL, TREE_CONFIG_MAX_BYTES, TREE_MULTI, VERSION
from .export import ExportOptions
from .media import MediaHandlerBase
from .snapshot import consistent_read

FORMAT_VERSION = 1
BACKUP_EXTENSION = ".tar"
MANIFEST_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

MANIFEST_NAME = "backup.json"
DATA_NAME = "data.gramps"
TREE_NAME = "tree.json"
USERS_NAME = "users.json"
MEDIA_NAME = "media.json"
MEMBER_NAMES = (DATA_NAME, TREE_NAME, USERS_NAME, MEDIA_NAME)

# the JSON members that are read into memory on restore
MAX_JSON_BYTES = 16 * 1024 * 1024

# restored users never get a higher role than tree owners may assign
MAX_RESTORED_ROLE = ROLE_OWNER


class BackupError(ValueError):
    """The file is not a valid backup archive or can't be restored here."""


@dataclass
class Backup:
    """The validated contents of a backup archive that a restore reads."""

    manifest: dict[str, Any]
    tree_config: dict[str, Any]
    users: list[dict[str, Any]]


def write_backup(
    db_handle: DbReadBase,
    tree: str,
    tree_name: str,
    file_path: str,
    user: UserBase | None = None,
) -> dict[str, Any]:
    """Write a backup archive of the tree to `file_path` and return its manifest.

    `db_handle` must be able to see private records. The Gramps data, the
    object counts and the media list come from one consistent snapshot.
    """
    created = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="gramps-backup-") as directory:
        data_path = os.path.join(directory, DATA_NAME)
        with consistent_read(db_handle) as snapshot_db:
            _export_xml(snapshot_db, data_path, user=user)
            object_counts = {
                plural: getattr(snapshot_db, f"get_number_of_{plural}")()
                for plural in GRAMPS_OBJECT_PLURAL.values()
            }
            media = [_media_entry(obj) for obj in snapshot_db.iter_media()]
            schema_version = snapshot_db.get_schema_version()
        json_members = {
            TREE_NAME: _json_bytes({"config": get_tree_config(tree)}),
            USERS_NAME: _json_bytes(_get_users(tree)),
            MEDIA_NAME: _json_bytes(media),
        }
        contents = [
            {
                "name": DATA_NAME,
                "size": os.path.getsize(data_path),
                "sha256": _sha256_file(data_path),
            }
        ] + [
            {
                "name": name,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in json_members.items()
        ]
        manifest = {
            "format_version": FORMAT_VERSION,
            "created": created.strftime(MANIFEST_DATE_FORMAT),
            "tree": {"id": tree, "name": tree_name},
            "versions": {
                "gramps_webapi": VERSION,
                "gramps": ENV["VERSION"],
                "db_schema": schema_version,
            },
            "backend": type(db_handle).__name__.lower(),
            "object_counts": object_counts,
            "media": {"count": len(media)},
            "contents": contents,
            "protected": False,
        }
        # never leave a partial archive under the final name
        partial_path = f"{file_path}.part"
        try:
            with tarfile.open(partial_path, "w") as tar:
                _add_bytes(tar, MANIFEST_NAME, _json_bytes(manifest), created)
                tar.add(data_path, arcname=DATA_NAME)
                for name, content in json_members.items():
                    _add_bytes(tar, name, content, created)
            os.replace(partial_path, file_path)
        except BaseException:
            if os.path.exists(partial_path):
                os.remove(partial_path)
            raise
    return manifest


def _export_xml(db_handle: DbReadBase, file_path: str, user: UserBase | None) -> None:
    """Export the whole database, unfiltered, as gzipped Gramps XML."""
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_export_plugins():
        if plugin.get_extension() == "gramps":
            export_function = plugin.get_export_function()
            break
    else:
        raise RuntimeError("Gramps XML exporter not found")
    if user is None:
        user = User()
    # the default options apply no filters and compress the file
    if not export_function(db_handle, file_path, user, ExportOptions()):
        raise RuntimeError("Gramps XML export failed")


def _media_entry(obj: Media) -> dict[str, Any]:
    return {
        "handle": obj.handle,
        "gramps_id": obj.gramps_id,
        "path": obj.path,
        "checksum": obj.checksum,
        "mime": obj.mime,
    }


def _get_users(tree: str) -> list[dict[str, Any]]:
    """Return the tree's users without IDs or credentials."""
    # in a single-tree setup, users may have no tree ID; in a multi-tree setup,
    # users without a tree are site admins, who don't belong to the tree
    is_single = current_app.config["TREE"] != TREE_MULTI
    users = get_all_user_details(tree=tree, include_treeless=is_single)
    return [
        {
            "name": user["name"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"],
        }
        for user in users
    ]


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")


def _add_bytes(tar: tarfile.TarFile, name: str, content: bytes, mtime: datetime):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mtime = int(mtime.timestamp())
    tar.addfile(info, io.BytesIO(content))


def _sha256_file(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def read_backup(file_path: str, verify: bool = True) -> Backup:
    """Validate a backup archive and return what a restore needs from it.

    The archive is untrusted input. Raises `BackupError` if it is not a valid
    backup archive or can't be restored on this server. With `verify`, the
    members' sizes and checksums are compared with the manifest.
    """
    try:
        with tarfile.open(file_path, "r:") as tar:
            members = _get_members(tar)
            manifest = _read_json(tar, members[MANIFEST_NAME])
            _validate_manifest(manifest)
            listed = {entry["name"]: entry for entry in manifest["contents"]}
            if set(listed) != set(members) - {MANIFEST_NAME}:
                raise BackupError("The archive's contents don't match its manifest")
            if verify:
                for name, entry in listed.items():
                    _verify_member(tar, members[name], entry)
            tree_config = _read_json(tar, members[TREE_NAME])
            users = _read_json(tar, members[USERS_NAME])
    except (tarfile.TarError, EOFError) as exc:
        raise BackupError("The file is not a valid backup archive") from exc
    return Backup(
        manifest=manifest,
        tree_config=_validate_tree_config(tree_config),
        users=_validate_users(users),
    )


def is_restorable(manifest: dict[str, Any]) -> bool:
    """Return whether this server can restore a backup with this manifest."""
    try:
        _validate_manifest(manifest)
    except BackupError:
        return False
    return True


def read_manifest(file_path: str) -> dict[str, Any]:
    """Return a stored archive's manifest without validating it for restore.

    For listing stored backups, so that a backup this server can't restore
    (e.g. after a downgrade) is still listed rather than hidden.
    """
    try:
        with tarfile.open(file_path, "r:") as tar:
            manifest = _read_json(tar, _get_members(tar)[MANIFEST_NAME])
    except (tarfile.TarError, EOFError) as exc:
        raise BackupError("The file is not a valid backup archive") from exc
    if not isinstance(manifest, dict):
        raise BackupError("Invalid manifest")
    return manifest


def extract_data(file_path: str, directory: str) -> str:
    """Copy the archive's Gramps XML file into `directory` and return its path."""
    target_path = os.path.join(directory, DATA_NAME)
    try:
        with tarfile.open(file_path, "r:") as tar:
            member = _get_members(tar)[DATA_NAME]
            source = tar.extractfile(member)
            assert source is not None  # mypy; members are regular files
            with source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
    except (tarfile.TarError, EOFError) as exc:
        raise BackupError("The file is not a valid backup archive") from exc
    return target_path


def _get_members(tar: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    """Return the archive's members by name, rejecting anything unexpected."""
    members: dict[str, tarfile.TarInfo] = {}
    for member in tar.getmembers():
        if member.name not in (MANIFEST_NAME,) + MEMBER_NAMES:
            raise BackupError(f"Unexpected file in the archive: {member.name}")
        if not member.isfile():
            raise BackupError(f"Not a regular file in the archive: {member.name}")
        if member.name in members:
            raise BackupError(f"Duplicate file in the archive: {member.name}")
        members[member.name] = member
    missing = [name for name in (MANIFEST_NAME,) + MEMBER_NAMES if name not in members]
    if missing:
        raise BackupError(f"Missing from the archive: {', '.join(missing)}")
    return members


def _read_json(tar: tarfile.TarFile, member: tarfile.TarInfo) -> Any:
    if member.size > MAX_JSON_BYTES:
        raise BackupError(f"{member.name} is too large")
    source = tar.extractfile(member)
    assert source is not None  # mypy; members are regular files
    with source:
        try:
            return json.loads(source.read())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError(f"{member.name} is not valid JSON") from exc


def _validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise BackupError("Invalid manifest")
    format_version = manifest.get("format_version")
    if not isinstance(format_version, int) or isinstance(format_version, bool):
        raise BackupError("Invalid manifest")
    if format_version > FORMAT_VERSION:
        raise BackupError(
            "The backup was made with a newer version of Gramps Web "
            "and can't be restored on this server"
        )
    if manifest.get("protected"):
        raise BackupError("Encrypted backups are not supported")
    versions = manifest.get("versions")
    db_schema = versions.get("db_schema") if isinstance(versions, dict) else None
    if not isinstance(db_schema, int) or isinstance(db_schema, bool):
        raise BackupError("Invalid manifest")
    if db_schema > DbGeneric.VERSION[0]:
        raise BackupError(
            "The backup was made with a newer database schema "
            "and can't be restored on this server"
        )
    contents = manifest.get("contents")
    if not isinstance(contents, list) or not all(
        isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and isinstance(entry.get("size"), int)
        and isinstance(entry.get("sha256"), str)
        for entry in contents
    ):
        raise BackupError("Invalid manifest")
    names = [entry["name"] for entry in contents]
    if len(names) != len(set(names)):
        raise BackupError("Invalid manifest")


def _verify_member(
    tar: tarfile.TarFile, member: tarfile.TarInfo, entry: dict[str, Any]
) -> None:
    if member.size != entry["size"]:
        raise BackupError(f"{member.name} is truncated or corrupted")
    source = tar.extractfile(member)
    assert source is not None  # mypy; members are regular files
    sha256 = hashlib.sha256()
    with source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha256.update(chunk)
    if sha256.hexdigest() != entry["sha256"]:
        raise BackupError(f"{member.name} is truncated or corrupted")


def _validate_tree_config(tree_json: Any) -> dict[str, Any]:
    config = tree_json.get("config") if isinstance(tree_json, dict) else None
    if not isinstance(config, dict):
        raise BackupError(f"Invalid {TREE_NAME}")
    if len(json.dumps(config).encode("utf-8")) > TREE_CONFIG_MAX_BYTES:
        raise BackupError(f"The tree settings in {TREE_NAME} are too large")
    return config


def _validate_users(users: Any) -> list[dict[str, Any]]:
    if not isinstance(users, list):
        raise BackupError(f"Invalid {USERS_NAME}")
    for user in users:
        if not (
            isinstance(user, dict)
            and isinstance(user.get("name"), str)
            and user["name"]
            and isinstance(user.get("full_name"), (str, type(None)))
            and isinstance(user.get("email"), (str, type(None)))
            and isinstance(user.get("role"), int)
            and not isinstance(user["role"], bool)
            and user["role"] in PERMISSIONS
        ):
            raise BackupError(f"Invalid {USERS_NAME}")
    return users


def restore_tree_config(
    tree: str, config: dict[str, Any], dry_run: bool = False
) -> dict[str, bool]:
    """Replace the tree's settings with the ones from the backup."""
    changed = get_tree_config(tree) != config
    if changed and not dry_run:
        set_tree_config(tree=tree, config=config)
    return {"changed": changed}


def restore_users(
    tree: str, users: list[dict[str, Any]], dry_run: bool = False
) -> dict[str, list[str]]:
    """Add the backup's users that don't exist yet to the tree.

    Usernames are unique across the server, so existing users, whichever tree
    they belong to, are skipped and never changed. Restored users get a random
    password and a role of at most tree owner.
    """
    added: list[str] = []
    skipped: list[str] = []
    for user in users:
        name = user["name"]
        if name in added or _user_exists(name):
            skipped.append(name)
            continue
        if not dry_run:
            try:
                add_user(
                    name=name,
                    password=secrets.token_urlsafe(16),
                    fullname=user["full_name"],
                    email=user["email"],
                    role=min(user["role"], MAX_RESTORED_ROLE),
                    tree=tree,
                )
            except ValueError:
                # created concurrently
                skipped.append(name)
                continue
        added.append(name)
    return {"added": added, "skipped": skipped}


def _user_exists(name: str) -> bool:
    try:
        get_guid(name)
    except ValueError:
        return False
    return True


def find_missing_media(
    media_handler: MediaHandlerBase, db_handle: DbReadBase
) -> list[str]:
    """Return the Gramps IDs of the media objects whose files don't exist."""
    objects = list(db_handle.iter_media())
    existing = {
        obj.handle
        for obj in media_handler.filter_existing_files(objects, db_handle=db_handle)
    }
    return sorted(obj.gramps_id for obj in objects if obj.handle not in existing)
