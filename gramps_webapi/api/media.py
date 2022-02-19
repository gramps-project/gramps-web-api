"""Generic media handler."""

import os
from pathlib import Path
from typing import BinaryIO, List, Optional

from flask import current_app
from gramps.gen.lib import Media

from ..types import FilenameOrPath
from ..util import get_extension
from .file import FileHandler, LocalFileHandler, upload_file_local
from .s3 import ObjectStorageFileHandler, filter_existing_files_s3, upload_file_s3
from .util import get_media_base_dir


class MediaHandler:
    """Generic handler for media files."""

    PREFIX_S3 = "s3://"
    TYPE_S3 = "s3"
    TYPE_LOCAL = "local"

    def __init__(self, base_dir: str):
        """Initialize given a base dir or URL."""
        self.base_dir = base_dir or ""
        self.repo_type = self._get_repo_type()

    def _get_repo_type(self) -> str:
        """Get the type of repository."""
        if self.base_dir.startswith(self.PREFIX_S3):
            return self.TYPE_S3
        return self.TYPE_LOCAL

    def _get_local_file_handler(self, handle) -> LocalFileHandler:
        """Get a local file handler."""
        return LocalFileHandler(handle, base_dir=self.base_dir)

    def _get_s3_file_handler(self, handle) -> ObjectStorageFileHandler:
        """Get an S3 file handler."""
        bucket_name = self._get_s3_bucket_name()
        endpoint_url = self._get_s3_endpoint_url()
        return ObjectStorageFileHandler(
            handle, bucket_name=bucket_name, endpoint_url=endpoint_url
        )

    def _get_s3_endpoint_url(self) -> Optional[str]:
        """Get the endpoint URL (or None) in case of S3."""
        return current_app.config.get("AWS_ENDPOINT_URL") or os.getenv(
            "AWS_ENDPOINT_URL"
        )

    def _get_s3_bucket_name(self) -> str:
        """Get the bucket name in case of S3."""
        if self.base_dir.startswith(self.PREFIX_S3):
            bucket_name = self.base_dir[len(self.PREFIX_S3) :]
        else:
            raise ValueError(f"Invalid object storage URL: {self.base_dir}")
        return bucket_name

    def get_file_handler(self, handle) -> FileHandler:
        """Get an appropriate file handler."""
        if self.repo_type == self.TYPE_S3:
            return self._get_s3_file_handler(handle)
        return self._get_local_file_handler(handle)

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
        if self.repo_type == self.TYPE_S3:
            bucket_name = self._get_s3_bucket_name()
            endpoint_url = self._get_s3_endpoint_url()
            upload_file_s3(
                bucket_name, stream, checksum, mime, endpoint_url=endpoint_url
            )
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
        if self.repo_type == self.TYPE_S3:
            # for S3, we use the bucket-level list of handles to avoid having
            # to do many GETs that are more expensive than one LIST
            bucket_name = self._get_s3_bucket_name()
            endpoint_url = self._get_s3_endpoint_url()
            return filter_existing_files_s3(
                bucket_name, objects, endpoint_url=endpoint_url
            )
        return [
            obj for obj in objects if self.get_file_handler(obj.handle).file_exists()
        ]
