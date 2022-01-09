"""Generic media handler."""

import os

from flask import current_app

from .file import FileHandler, LocalFileHandler
from .s3 import ObjectStorageFileHandler


class MediaHandler:
    """Generic handler for media files."""

    PREFIX_S3 = "s3://"

    def __init__(self, base_dir: str):
        """Initialize given a base dir or URL."""
        self.base_dir = base_dir

    def get_file_handler(self, handle) -> FileHandler:
        """Get an appropriate file handler."""
        if self.base_dir.startswith(self.PREFIX_S3):
            return self._get_s3_file_handler(handle)
        return self._get_local_file_handler(handle)

    def _get_local_file_handler(self, handle) -> LocalFileHandler:
        """Get a local file handler."""
        return LocalFileHandler(handle, base_dir=self.base_dir)

    def _get_s3_file_handler(self, handle) -> ObjectStorageFileHandler:
        """Get an S3 file handler."""
        if self.base_dir.startswith(self.PREFIX_S3):
            bucket_name = self.base_dir[len(self.PREFIX_S3) :]
        else:
            raise ValueError(f"Invalid object storage URL: {self.base_dir}")
        endpoint_url = current_app.config.get("AWS_ENDPOINT_URL") or os.getenv(
            "AWS_ENDPOINT_URL"
        )
        return ObjectStorageFileHandler(
            handle, bucket_name=bucket_name, endpoint_url=endpoint_url
        )
