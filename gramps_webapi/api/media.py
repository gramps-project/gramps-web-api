"""Generic media handler."""

import os
from typing import BinaryIO, Optional

from flask import current_app

from .file import FileHandler, LocalFileHandler, upload_file_local
from .s3 import ObjectStorageFileHandler, upload_file_s3


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

    def upload_file(self, stream: BinaryIO, checksum: str, mime: str) -> str:
        """Upload a file from a stream, returning the relative file path."""
        if self.repo_type == self.TYPE_S3:
            bucket_name = self._get_s3_bucket_name()
            endpoint_url = self._get_s3_endpoint_url()
            return upload_file_s3(
                bucket_name, stream, checksum, mime, endpoint_url=endpoint_url
            )
        return upload_file_local(self.base_dir, stream, checksum, mime)
