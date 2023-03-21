"""Generic media handler."""

import os
from pathlib import Path
from typing import BinaryIO, List, Optional, Set

from flask import current_app
from gramps.gen.lib import Media

from ..types import FilenameOrPath
from ..util import get_extension
from .file import FileHandler, LocalFileHandler, upload_file_local
from .s3 import ObjectStorageFileHandler, list_object_keys, upload_file_s3
from .util import get_media_base_dir


PREFIX_S3 = "s3://"


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
        base_dir = self.base_dir or get_media_base_dir()
        if path is not None:
            if Path(path).is_absolute():
                # Don't allow absolute paths! This will raise
                # if path is not relative to base_dir
                rel_path: FilenameOrPath = Path(path).relative_to(base_dir)
            else:
                rel_path = path
            upload_file_local(base_dir, rel_path, stream)
        else:
            rel_path = self.get_default_filename(checksum, mime)
            upload_file_local(base_dir, rel_path, stream)

    def filter_existing_files(self, objects: List[Media]) -> List[Media]:
        """Given a list of media objects, return the ones with existing files."""
        return [
            obj for obj in objects if self.get_file_handler(obj.handle).file_exists()
        ]


class MediaHandlerS3(MediaHandlerBase):
    """Generic handler for object storage media files."""

    CACHE_FILENAME = "s3_key_cache"

    def __init__(self, base_dir: str):
        """Initialize given a base dir or URL."""
        if not base_dir.startswith(PREFIX_S3):
            raise ValueError(f"Invalid object storage URL: {self.base_dir}")
        super().__init__(base_dir)

    @property
    def endpoint_url(self) -> Optional[str]:
        """Get the endpoint URL (or None)."""
        return current_app.config.get("AWS_ENDPOINT_URL") or os.getenv(
            "AWS_ENDPOINT_URL"
        )

    @property
    def bucket_name(self) -> str:
        """Get the bucket name."""
        return self.base_dir[len(PREFIX_S3) :]

    def _cache_get_keys(self) -> Set[str]:
        """Get the cached object keys."""
        if os.path.isfile(self.CACHE_FILENAME):
            with open(self.CACHE_FILENAME, "r", encoding="utf-8") as f_cache:
                keys = f_cache.read.splitlines()
                if keys:
                    return set(keys)
        return set()

    def _cache_add_key(self, key: str) -> None:
        """Add a key to the cache."""

    def _cache_set(self, keys: List[str]) -> None:
        """Add a key to the cache."""
        with open(self.CACHE_FILENAME, "w", encoding="utf-8") as f_cache:
            for key in keys:
                f_cache.write(key)

    @property
    def remote_keys(self) -> Set[str]:
        """Return the set of all object keys that are known to exist on remote."""
        keys = self._cache_get_keys()
        if keys:
            return keys
        keys = list_object_keys(self.bucket_name, endpoint_url=self.endpoint_url)
        self._cache_set(keys)
        return set(keys)

    def get_file_handler(self, handle) -> ObjectStorageFileHandler:
        """Get an S3 file handler."""
        return ObjectStorageFileHandler(
            handle, bucket_name=self.bucket_name, endpoint_url=self.endpoint_url
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
            self.bucket_name, stream, checksum, mime, endpoint_url=self.endpoint_url
        )
        self._cache_add_key(checksum)

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
