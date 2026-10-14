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

"""Storage of backup archives."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

from flask import current_app

from .backup import BACKUP_EXTENSION, BackupError, is_restorable, read_manifest
from .util import abort_with_message

BACKUP_ID_PATTERN = re.compile(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
)


class LocalBackupStore:
    """Backup archives in a local directory, with a subdirectory per tree.

    Only complete archives have the archive extension (`write_backup` renames
    them when done), so the directory can safely be synced with a tool like
    rclone that ignores the partial files.
    """

    def __init__(self, directory: str):
        """Initialize given the base directory."""
        self.directory = os.path.abspath(directory)

    def _tree_dir(self, tree: str) -> Path:
        return Path(self.directory) / tree

    def new_path(self, tree: str) -> tuple[str, str]:
        """Return the ID and path for a new archive of the tree."""
        tree_dir = self._tree_dir(tree)
        tree_dir.mkdir(parents=True, exist_ok=True)
        backup_id = str(uuid.uuid4())
        return backup_id, str(tree_dir / f"{backup_id}{BACKUP_EXTENSION}")

    def get_path(self, tree: str, backup_id: str) -> str | None:
        """Return the path of an archive of the tree, or None if there is none."""
        if not BACKUP_ID_PATTERN.fullmatch(backup_id):
            return None
        path = self._tree_dir(tree) / f"{backup_id}{BACKUP_EXTENSION}"
        if not path.is_file():
            return None
        return str(path)

    def list_backups(self, tree: str) -> list[dict[str, Any]]:
        """Return the tree's archives, newest first."""
        return [
            {
                "id": path.stem,
                "size": size,
                "restorable": is_restorable(manifest),
                "manifest": manifest,
            }
            for path, size, manifest in self._newest_first(tree)
        ]

    def delete(self, tree: str, backup_id: str) -> bool:
        """Delete an archive of the tree; return whether it existed."""
        path = self.get_path(tree, backup_id)
        if path is None:
            return False
        try:
            os.remove(path)
        except FileNotFoundError:
            return False
        return True

    def prune(self, tree: str, keep: int) -> None:
        """Delete all but the newest `keep` archives of the tree (at least one).

        Files whose manifest can't be read are left alone.
        """
        for path, _size, _manifest in self._newest_first(tree)[max(keep, 1) :]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def _newest_first(self, tree: str) -> list[tuple[Path, int, dict[str, Any]]]:
        """Return the tree's archives with their sizes and manifests, newest first.

        Ordered by the manifest's creation time, which unlike the file's
        modification time survives copying the archive elsewhere.
        """
        archives = []
        for path in self._paths(tree):
            try:
                size = path.stat().st_size
                manifest = read_manifest(str(path))
            except (BackupError, OSError):
                continue  # deleted concurrently, or not an archive
            archives.append((path, size, manifest))
        # the ID makes the order deterministic for equal creation times
        archives.sort(
            key=lambda archive: (str(archive[2].get("created")), archive[0].stem),
            reverse=True,
        )
        return archives

    def _paths(self, tree: str) -> list[Path]:
        tree_dir = self._tree_dir(tree)
        if not tree_dir.is_dir():
            return []
        return [
            path
            for path in tree_dir.glob(f"*{BACKUP_EXTENSION}")
            if BACKUP_ID_PATTERN.fullmatch(path.stem)
        ]


def backups_enabled() -> bool:
    """Return whether a backup directory is configured."""
    return bool(current_app.config["BACKUP_DIR"])


def get_backup_store() -> LocalBackupStore:
    """Return the configured backup store, or abort if there is none.

    Requires the app context.
    """
    if not backups_enabled():
        abort_with_message(501, "No backup directory is configured")
    return LocalBackupStore(current_app.config["BACKUP_DIR"])
