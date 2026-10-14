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

"""Backup archive API resources."""

import os
import shutil
import uuid
from datetime import datetime

from flask import abort, current_app, jsonify, send_file
from flask_jwt_extended import get_jwt_identity
from marshmallow import Schema
from webargs import fields
from werkzeug.utils import secure_filename

from ...auth.const import (
    PERM_ADD_USER,
    PERM_DEL_OBJ_BATCH,
    PERM_EDIT_TREE,
    PERM_IMPORT_FILE,
    PERM_MANAGE_BACKUPS,
)
from ...types import ResponseReturnValue
from ..auth import require_permissions
from ..backup import (
    BACKUP_EXTENSION,
    MANIFEST_DATE_FORMAT,
    BackupError,
    read_backup,
    read_manifest,
)
from ..backup_store import get_backup_store
from ..blueprint import api_blueprint
from ..ratelimiter import limiter_per_tree
from ..tasks import (
    AsyncResult,
    create_backup,
    make_task_response,
    restore_backup_archive,
    run_task,
)
from ..util import (
    abort_with_message,
    remove_file_on_error,
    get_db_handle,
    get_db_manager,
    get_tree_from_jwt_or_fail,
)
from . import FreshProtectedResource, ProtectedResource
from .importers import stream_upload_to_tempfile
from .schemas import BackupRestoreResultSchema, BackupSchema


def get_limit() -> str:
    """Get the rate limit string for creating backups."""
    return current_app.config["RATE_LIMIT_BACKUP"]


class BackupsResource(ProtectedResource):
    """Stored backups of the tree."""

    @api_blueprint.response(200, BackupSchema(many=True))
    @api_blueprint.arguments(Schema(), location="query")
    def get(self, args) -> ResponseReturnValue:
        """List the tree's stored backups, newest first."""
        require_permissions([PERM_MANAGE_BACKUPS])
        return (
            jsonify(get_backup_store().list_backups(get_tree_from_jwt_or_fail())),
            200,
        )

    @api_blueprint.response(201, BackupSchema())
    @api_blueprint.arguments(Schema(), location="query")
    # only accepted requests count, not rejected ones (e.g. 403, 409)
    @limiter_per_tree.limit(
        get_limit, deduct_when=lambda response: response.status_code in (201, 202)
    )
    def post(self, args) -> ResponseReturnValue:
        """Create a stored backup of the tree.

        The oldest backups beyond the number the server keeps per tree are
        deleted.
        """
        require_permissions([PERM_MANAGE_BACKUPS])
        get_db_handle()  # needed to load plugins
        task = run_task(
            create_backup,
            tree=get_tree_from_jwt_or_fail(),
            user_id=get_jwt_identity(),
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 201


class BackupResource(ProtectedResource):
    """A stored backup of the tree."""

    def get(self, backup_id: str) -> ResponseReturnValue:
        """Download a stored backup archive."""
        require_permissions([PERM_MANAGE_BACKUPS])
        tree = get_tree_from_jwt_or_fail()
        file_path = get_backup_store().get_path(tree, backup_id)
        if file_path is None:
            abort(404)
        try:
            manifest = read_manifest(file_path)
        except (BackupError, OSError):
            abort(404)
        tree_name = secure_filename(get_db_manager(tree).name) or "tree"
        try:
            created = datetime.strptime(manifest["created"], MANIFEST_DATE_FORMAT)
            suffix = f"{created:%Y%m%d-%H%M%S}"
        except (KeyError, TypeError, ValueError):
            suffix = backup_id
        # streamed from disk, with support for resuming via range requests
        return send_file(
            file_path,
            mimetype="application/x-tar",
            as_attachment=True,
            download_name=f"gramps-web-backup-{tree_name}-{suffix}{BACKUP_EXTENSION}",
        )

    def delete(self, backup_id: str) -> ResponseReturnValue:
        """Delete a stored backup."""
        require_permissions([PERM_MANAGE_BACKUPS])
        if not get_backup_store().delete(get_tree_from_jwt_or_fail(), backup_id):
            abort(404)
        return "", 204


class BackupRestoreQueryArgs(Schema):
    """Query arguments for restoring a backup."""

    jwt = fields.String(
        required=False,
        metadata={"description": "JWT token for upload authentication."},
    )
    dry_run = fields.Boolean(
        load_default=False,
        metadata={
            "description": (
                "If true, return what the restore would change without "
                "changing anything."
            )
        },
    )
    data = fields.Boolean(
        load_default=True,
        metadata={
            "description": (
                "If true (default), reset the family tree data to the backup's."
            )
        },
    )
    tree_settings = fields.Boolean(
        load_default=True,
        metadata={
            "description": (
                "If true (default), replace the tree settings with the backup's."
            )
        },
    )
    users = fields.Boolean(
        load_default=True,
        metadata={
            "description": (
                "If true (default), add the backup's users that don't exist yet."
            )
        },
    )


def _require_restore_permissions(args: dict) -> None:
    """Require the permissions for restoring the selected components."""
    permissions = []
    if args["data"]:
        permissions += [PERM_IMPORT_FILE, PERM_DEL_OBJ_BATCH]
    if args["tree_settings"]:
        permissions.append(PERM_EDIT_TREE)
    if args["users"]:
        permissions.append(PERM_ADD_USER)
    if not permissions:
        abort_with_message(422, "Nothing selected to restore")
    require_permissions(permissions)


def _restore(args: dict, tree: str, file_path: str):
    """Validate the archive, then restore the selected components from it.

    `file_path` is the restore's own copy, which the task deletes when done.
    """
    with remove_file_on_error(file_path):
        try:
            read_backup(file_path)
        except BackupError as exc:
            abort_with_message(422, str(exc))
        task = run_task(
            restore_backup_archive,
            tree=tree,
            user_id=get_jwt_identity(),
            file_name=file_path,
            data=args["data"],
            tree_settings=args["tree_settings"],
            users=args["users"],
            dry_run=args["dry_run"],
        )
    if isinstance(task, AsyncResult):
        return make_task_response(task)
    return jsonify(task), 200


def _copy_to_tempfile(source_path: str) -> str:
    """Copy a stored archive to where uploads go and return the copy's path.

    The restore then never touches the stored archive, which may be deleted
    by pruning while the restore runs.
    """
    export_path = current_app.config["EXPORT_DIR"]
    os.makedirs(export_path, exist_ok=True)
    file_path = os.path.join(export_path, f"{uuid.uuid4()}{BACKUP_EXTENSION}")
    try:
        shutil.copyfile(source_path, file_path)
    except FileNotFoundError:
        # pruned in the meantime
        abort(404)
    return file_path


class BackupRestoreResource(FreshProtectedResource):
    """Restore the tree from a stored backup."""

    @api_blueprint.response(200, BackupRestoreResultSchema())
    @api_blueprint.arguments(BackupRestoreQueryArgs, location="query")
    def post(self, args: dict, backup_id: str) -> ResponseReturnValue:
        """Restore the selected parts of the tree from a stored backup."""
        _require_restore_permissions(args)
        get_db_handle()  # needed to load plugins
        tree = get_tree_from_jwt_or_fail()
        stored_path = get_backup_store().get_path(tree, backup_id)
        if stored_path is None:
            abort(404)
        return _restore(args, tree=tree, file_path=_copy_to_tempfile(stored_path))


class BackupUploadRestoreResource(FreshProtectedResource):
    """Restore the tree from an uploaded backup archive."""

    @api_blueprint.response(200, BackupRestoreResultSchema())
    @api_blueprint.arguments(BackupRestoreQueryArgs, location="query")
    def post(self, args: dict) -> ResponseReturnValue:
        """Restore the selected parts of the tree from an uploaded backup archive."""
        _require_restore_permissions(args)
        get_db_handle()  # needed to load plugins
        tree = get_tree_from_jwt_or_fail()
        file_path = stream_upload_to_tempfile(BACKUP_EXTENSION.lstrip("."))
        return _restore(args, tree=tree, file_path=file_path)
