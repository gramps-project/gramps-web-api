"""Generic media handler."""

import os
from pathlib import Path
from typing import BinaryIO, List, Optional, Set

from flask import current_app
from gramps.gen.lib import Media
from gramps.gen.utils.file import expand_media_path

from ..types import FilenameOrPath
from ..util import get_extension
from .file import FileHandler, LocalFileHandler, upload_file_local
from .s3 import ObjectStorageFileHandler, list_object_keys, upload_file_s3
from .util import get_db_handle


PREFIX_S3 = "s3://"


def removeprefix(string: str, prefix: str, /) -> str:
    """Remove prefix from a string; see PEP 616."""
    if string.startswith(prefix):
        return string[len(prefix) :]
    return string[:]


class MediaHandlerBase:
    """Generic handler for media files."""

    def __init__(self, base_dir: str):
        """Initialize given a base dir or URL."""
        self.base_dir = base_dir or ""

    def get_file_handler(self, handle) -> FileHandler:
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

    def filter_existing_files(self, objects: List[Media]) -> List[Media]:
        """Given a list of media objects, return the ones with existing files."""
        raise NotImplementedError


class MediaHandlerLocal(MediaHandlerBase):
    """Handler for local media files."""

    def get_file_handler(self, handle) -> LocalFileHandler:
        """Get a local file handler."""
        return LocalFileHandler(handle, base_dir=self.base_dir)

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
                rel_path: FilenameOrPath = Path(path).relative_to(base_dir)
            else:
                rel_path = path
            upload_file_local(self.base_dir, rel_path, stream)
        else:
            rel_path = self.get_default_filename(checksum, mime)
            upload_file_local(self.base_dir, rel_path, stream)

    def filter_existing_files(self, objects: List[Media]) -> List[Media]:
        """Given a list of media objects, return the ones with existing files."""
        return [
            obj for obj in objects if self.get_file_handler(obj.handle).file_exists()
        ]


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
        return removeprefix(self.base_dir, PREFIX_S3).split("/")[0]

    @property
    def prefix(self) -> Optional[str]:
        """Get the prefix."""
        splitted = removeprefix(self.base_dir, PREFIX_S3).split("/", 1)
        if len(splitted) < 2:
            return None
        return splitted[1].rstrip("/")

    @property
    def remote_keys(self) -> Set[str]:
        """Return the set of all object keys that are known to exist on remote."""
        keys = list_object_keys(self.bucket_name, endpoint_url=self.endpoint_url)
        return set(removeprefix(key, self.prefix or "").lstrip("/") for key in keys)

    def get_file_handler(self, handle) -> ObjectStorageFileHandler:
        """Get an S3 file handler."""
        return ObjectStorageFileHandler(
            handle,
            bucket_name=self.bucket_name,
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

    def filter_existing_files(self, objects: List[Media]) -> List[Media]:
        """Given a list of media objects, return the ones with existing files."""
        # for S3, we use the bucket-level list of handles to avoid having
        # to do many GETs that are more expensive than one LIST
        return [obj for obj in objects if obj.checksum in self.remote_keys]


def MediaHandler(base_dir: Optional[str]) -> MediaHandlerBase:
    """Return an appropriate media handler."""
    if base_dir and base_dir.startswith(PREFIX_S3):
        return MediaHandlerS3(base_dir=base_dir)
    return MediaHandlerLocal(base_dir=base_dir or "")


def get_media_handler(tree: Optional[str] = None) -> MediaHandlerBase:
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
            db = get_db_handle()
            base_dir = expand_media_path(db.get_mediapath(), db)
        if prefix:
            # construct subdirectory using OS dependent path join
            base_dir = os.path.join(base_dir, prefix)
    return MediaHandler(base_dir)
