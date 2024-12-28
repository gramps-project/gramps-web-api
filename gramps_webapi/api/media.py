#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021-2023      David Straub
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


"""Generic media handler."""

import os
import zipfile
from pathlib import Path
from typing import BinaryIO, Callable, List, Optional, Set

from flask import current_app
from flask_jwt_extended import get_jwt_identity
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import Media
from gramps.gen.utils.file import expand_media_path

from ..auth import get_tree_usage, set_tree_usage
from ..types import FilenameOrPath
from ..util import get_extension
from .file import FileHandler, LocalFileHandler, upload_file_local
from .s3 import ObjectStorageFileHandler, get_object_keys_size, upload_file_s3
from .util import (
    abort_with_message,
    close_db,
    get_db_handle,
    get_db_outside_request,
    get_tree_from_jwt,
    get_tree_from_jwt_or_fail,
)

PREFIX_S3 = "s3://"


class MediaHandlerBase:
    """Generic handler for media files."""

    def __init__(self, base_dir: str):
        """Initialize given a base dir or URL."""
        self.base_dir = base_dir or ""

    def get_file_handler(self, handle, db_handle: DbReadBase) -> FileHandler:
        """Get an appropriate file handler."""
        raise NotImplementedError

    @staticmethod
    def get_default_filename(checksum: str, mime: str) -> str:
        """Get the default file name for given checksum and MIME type."""
        if not mime:
            raise ValueError("Missing MIME type")
        ext = get_extension(mime)
        if not ext:
            raise ValueError("MIME type not recognized")
        return f"{checksum}{ext}"

    def upload_file(
        self,
        stream: BinaryIO,
        checksum: str,
        mime: str,
        path: Optional[FilenameOrPath] = None,
    ) -> None:
        """Upload a file from a stream."""
        raise NotImplementedError

    def filter_existing_files(
        self, objects: List[Media], db_handle: DbReadBase
    ) -> List[Media]:
        """Given a list of media objects, return the ones with existing files."""
        raise NotImplementedError

    def get_media_size(self, db_handle: Optional[DbReadBase] = None) -> int:
        """Return the total disk space used by all existing media objects."""
        raise NotImplementedError

    def create_file_archive(
        self,
        db_handle: DbReadBase,
        zip_filename: FilenameOrPath,
        include_private: bool,
        progress_cb: Optional[Callable] = None,
    ) -> None:
        """Create a ZIP archive on disk containing all media files."""
        raise NotImplementedError


class MediaHandlerLocal(MediaHandlerBase):
    """Handler for local media files."""

    def get_file_handler(self, handle, db_handle: DbReadBase) -> LocalFileHandler:
        """Get a local file handler."""
        return LocalFileHandler(handle, base_dir=self.base_dir, db_handle=db_handle)

    def upload_file(
        self,
        stream: BinaryIO,
        checksum: str,
        mime: str,
        path: Optional[FilenameOrPath] = None,
    ) -> None:
        """Upload a file from a stream."""
        if path is not None:
            if Path(path).is_absolute():
                # Don't allow absolute paths! This will raise
                # if path is not relative to base_dir
                rel_path: FilenameOrPath = Path(path).relative_to(self.base_dir)
            else:
                rel_path = path
            upload_file_local(self.base_dir, rel_path, stream)
        else:
            rel_path = self.get_default_filename(checksum, mime)
            upload_file_local(self.base_dir, rel_path, stream)

    def filter_existing_files(
        self, objects: List[Media], db_handle: DbReadBase
    ) -> List[Media]:
        """Given a list of media objects, return the ones with existing files."""
        return [
            obj
            for obj in objects
            if self.get_file_handler(obj.handle, db_handle=db_handle).file_exists()
        ]

    def get_media_size(self, db_handle: Optional[DbReadBase] = None) -> int:
        """Return the total disk space used by all existing media objects.

        Only works with a request context.
        """
        if not db_handle:
            db_handle = get_db_handle()
        if not os.path.isdir(self.base_dir):
            return 0
        size = 0
        paths_seen = set()
        for obj in db_handle.iter_media():
            path = obj.path
            if os.path.isabs(path):
                if Path(self.base_dir).resolve() not in Path(path).resolve().parents:
                    continue  # file outside base dir - ignore
            else:
                path = os.path.join(self.base_dir, path)
            if Path(path).is_file() and path not in paths_seen:
                file_size = os.path.getsize(path)
                size += file_size
                paths_seen.add(path)
        return size

    def create_file_archive(
        self,
        db_handle: DbReadBase,
        zip_filename: FilenameOrPath,
        include_private: bool,
        progress_cb: Optional[Callable] = None,
    ) -> None:
        """Create a ZIP archive on disk containing all media files."""
        if not os.path.isdir(self.base_dir):
            raise ValueError(f"Directory {self.base_dir} does not exist")
        paths_seen = set()
        if progress_cb:
            total = db_handle.get_number_of_media()
        with zipfile.ZipFile(zip_filename, "w") as zip_file:
            for i, obj in enumerate(db_handle.iter_media()):
                if progress_cb:
                    progress_cb(current=i, total=total)

                if not include_private and obj.private:
                    continue
                path = obj.path
                if os.path.isabs(path):
                    if (
                        Path(self.base_dir).resolve()
                        not in Path(path).resolve().parents
                    ):
                        continue  # file outside base dir - ignore
                else:
                    path = os.path.join(self.base_dir, path)
                rel_path = os.path.relpath(path, self.base_dir)
                if Path(path).is_file() and path not in paths_seen:
                    zip_file.write(path, arcname=rel_path)
                    paths_seen.add(path)


class MediaHandlerS3(MediaHandlerBase):
    """Generic handler for object storage media files."""

    def __init__(self, base_dir: str):
        """Initialize given a base dir or URL."""
        if not base_dir.startswith(PREFIX_S3):
            raise ValueError(f"Invalid object storage URL: {self.base_dir}")
        super().__init__(base_dir)

    @property
    def endpoint_url(self) -> Optional[str]:
        """Get the endpoint URL (or None)."""
        return os.getenv("AWS_ENDPOINT_URL")

    @property
    def bucket_name(self) -> str:
        """Get the bucket name."""
        return self.base_dir.removeprefix(PREFIX_S3).split("/")[0]

    @property
    def prefix(self) -> Optional[str]:
        """Get the prefix."""
        splitted = self.base_dir.removeprefix(PREFIX_S3).split("/", 1)
        if len(splitted) < 2:
            return None
        return splitted[1].rstrip("/")

    def get_remote_keys(self) -> Set[str]:
        """Return the set of all object keys that are known to exist on remote."""
        keys = get_object_keys_size(
            self.bucket_name, prefix=self.prefix, endpoint_url=self.endpoint_url
        )
        return set(key.removeprefix(self.prefix or "").lstrip("/") for key in keys)

    def get_file_handler(
        self, handle, db_handle: DbReadBase
    ) -> ObjectStorageFileHandler:
        """Get an S3 file handler."""
        return ObjectStorageFileHandler(
            handle,
            bucket_name=self.bucket_name,
            db_handle=db_handle,
            prefix=self.prefix,
            endpoint_url=self.endpoint_url,
        )

    def upload_file(
        self,
        stream: BinaryIO,
        checksum: str,
        mime: str,
        path: Optional[FilenameOrPath] = None,
    ) -> None:
        """Upload a file from a stream."""
        upload_file_s3(
            self.bucket_name,
            stream,
            checksum,
            mime,
            prefix=self.prefix,
            endpoint_url=self.endpoint_url,
        )

    def filter_existing_files(
        self, objects: List[Media], db_handle: DbReadBase
    ) -> List[Media]:
        """Given a list of media objects, return the ones with existing files."""
        # for S3, we use the bucket-level list of handles to avoid having
        # to do many GETs that are more expensive than one LIST
        remote_keys = self.get_remote_keys()
        return [obj for obj in objects if obj.checksum in remote_keys]

    def get_media_size(self, db_handle: Optional[DbReadBase] = None) -> int:
        """Return the total disk space used by all existing media objects."""
        if not db_handle:
            db_handle = get_db_handle()
        keys = set(obj.checksum for obj in db_handle.iter_media())
        keys_size = get_object_keys_size(
            bucket_name=self.bucket_name,
            prefix=self.prefix,
            endpoint_url=self.endpoint_url,
        )
        # remove prefix if needed
        if self.prefix:
            keys_size = {
                key.removeprefix(self.prefix).lstrip("/"): size
                for key, size in keys_size.items()
            }
        return sum(keys_size.get(key, 0) for key in keys)

    def create_file_archive(
        self,
        db_handle: DbReadBase,
        zip_filename: FilenameOrPath,
        include_private: bool,
        progress_cb: Optional[Callable] = None,
    ) -> None:
        """Create a ZIP archive on disk containing all media files."""
        remote_keys = self.get_remote_keys()
        if progress_cb:
            total = db_handle.get_number_of_media()
        with zipfile.ZipFile(zip_filename, "w") as zip_file:
            for i, obj in enumerate(db_handle.iter_media()):
                if progress_cb:
                    progress_cb(current=i, total=total)
                if not include_private and obj.private:
                    continue
                if obj.checksum not in remote_keys:
                    continue
                media_path = obj.path
                if os.path.isabs(media_path):
                    continue  # ignore absolute paths
                file_handler = self.get_file_handler(obj.handle, db_handle=db_handle)
                fobj = file_handler.get_file_object()
                zip_file.writestr(media_path, fobj.read())


def MediaHandler(base_dir: Optional[str]) -> MediaHandlerBase:
    """Return an appropriate media handler."""
    if base_dir and base_dir.startswith(PREFIX_S3):
        return MediaHandlerS3(base_dir=base_dir)
    return MediaHandlerLocal(base_dir=base_dir or "")


def get_media_handler(
    db_handle: DbReadBase, tree: Optional[str] = None
) -> MediaHandlerBase:
    """Get an appropriate media handler instance.

    Requires the flask app context and constructs base dir from config.
    """
    base_dir = current_app.config.get("MEDIA_BASE_DIR", "")
    if current_app.config.get("MEDIA_PREFIX_TREE"):
        if not tree:
            raise ValueError("Tree ID is required when MEDIA_PREFIX_TREE is True.")
        prefix = tree
    else:
        prefix = None
    if base_dir and base_dir.startswith(PREFIX_S3):
        if prefix:
            # for S3, always add prefix with slash
            base_dir = f"{base_dir}/{prefix}"
    else:
        if not base_dir:
            # use media base dir set in Gramps DB as fallback
            base_dir = expand_media_path(db_handle.get_mediapath(), db_handle)
        if prefix:
            # construct subdirectory using OS dependent path join
            base_dir = os.path.join(base_dir, prefix)
    return MediaHandler(base_dir)


def update_usage_media(
    tree: Optional[str] = None, user_id: Optional[str] = None
) -> int:
    """Update the usage of media."""
    if not tree:
        tree = get_tree_from_jwt_or_fail()
    if not user_id:
        user_id = get_jwt_identity()
    assert user_id is not None, "Unexpected error while looking up user ID."
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=True, user_id=user_id
    )
    try:
        media_handler = get_media_handler(db_handle, tree=tree)
        usage_media = media_handler.get_media_size(db_handle=db_handle)
    finally:
        close_db(db_handle)
    set_tree_usage(tree, usage_media=usage_media)
    return usage_media


def check_quota_media(
    to_add: int, tree: Optional[str] = None, user_id: Optional[str] = None
) -> None:
    """Check whether the quota allows adding `to_add` bytes and abort if not."""
    if not tree:
        tree = get_tree_from_jwt_or_fail()
    usage_dict = get_tree_usage(tree)
    if not usage_dict or usage_dict.get("usage_media") is None:
        update_usage_media(tree=tree, user_id=user_id)
        usage_dict = get_tree_usage(tree)
        assert usage_dict is not None, "Unexpected error while looking up usage data."
    usage = usage_dict["usage_media"]
    quota = usage_dict.get("quota_media")
    if quota is None:
        return
    if usage + to_add > quota:
        abort_with_message(405, "Not allowed by media quota")
