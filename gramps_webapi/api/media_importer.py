"""Class for handling the import of a media ZIP archive."""

import os
import shutil
import tempfile
import zipfile
from typing import Dict, List, Tuple

from gramps.gen.db.base import DbReadBase

from ..auth import set_tree_usage
from ..types import FilenameOrPath
from .file import get_checksum
from .media import check_quota_media, get_media_handler


class MediaImporter:
    def __init__(
        self,
        tree: str,
        db_handle: DbReadBase,
        file_name: FilenameOrPath,
        delete: bool = True,
    ) -> None:
        """Initialize media importer."""
        self.tree = tree
        self.db_handle = db_handle
        self.file_name = file_name
        self.delete = delete
        self.media_handler = get_media_handler(self.db_handle, tree=self.tree)
        self.objects = list(db_handle.iter_media())

    def _identify_missing_files(self) -> Dict[str, List[Tuple[str, str, str]]]:
        """Identify missing files by comparing existing handles with all media objects."""
        objects_existing = self.media_handler.filter_existing_files(
            self.objects, db_handle=self.db_handle
        )
        handles_existing = set(obj.handle for obj in objects_existing)
        objects_missing = [
            obj for obj in self.objects if obj.handle not in handles_existing
        ]

        checksums_handles = {}
        for obj in objects_missing:
            if obj.checksum not in checksums_handles:
                checksums_handles[obj.checksum] = []
            obj_details = (obj.handle, obj.get_path(), obj.get_mime_type())
            checksums_handles[obj.checksum].append(obj_details)

        return checksums_handles

    def _check_disk_space_and_extract(self) -> str:
        """Check disk space and extract files into a temporary directory."""
        total_size = 0
        with zipfile.ZipFile(self.file_name, "r") as zip_file:
            for file_info in zip_file.infolist():
                total_size += file_info.file_size

            disk_usage = shutil.disk_usage(self.file_name)
            if total_size > disk_usage.free:
                raise ValueError("Not enough free space on disk")

            temp_dir = tempfile.mkdtemp()
            zip_file.extractall(temp_dir)

        return temp_dir

    def _identify_files_to_upload(
        self, temp_dir: str, checksums_handles: Dict[str, List[Tuple[str, str, str]]]
    ) -> Dict[str, Tuple[str, int]]:
        """Identify files to upload from the extracted temporary directory."""
        to_upload = {}
        for root, _, files in os.walk(temp_dir):
            for name in files:
                file_path = os.path.join(root, name)
                with open(file_path, "rb") as f:
                    checksum = get_checksum(f)
                    if checksum in checksums_handles and checksum not in to_upload:
                        to_upload[checksum] = (file_path, os.path.getsize(file_path))

        return to_upload

    def _upload_files(
        self,
        to_upload: Dict[str, Tuple[str, int]],
        checksums_handles: Dict[str, List[Tuple[str, str, str]]],
    ) -> int:
        """Upload identified files and return the number of failures."""
        num_failures = 0
        for checksum, (file_path, file_size) in to_upload.items():
            for handle, media_path, mime in checksums_handles[checksum]:
                with open(file_path, "rb") as f:
                    try:
                        self.media_handler.upload_file(
                            f, checksum, mime, path=media_path
                        )
                    except Exception:
                        num_failures += 1

        return num_failures

    def _delete_zip_file(self):
        """Delete the ZIP file."""
        return os.remove(self.file_name)

    def _delete_temporary_directory(self, temp_dir):
        """Delete the temporary directory."""
        return shutil.rmtree(temp_dir)

    def _update_media_usage(self) -> None:
        """Update the media usage."""
        usage_media = self.media_handler.get_media_size(db_handle=self.db_handle)
        set_tree_usage(self.tree, usage_media=usage_media)

    def run(self) -> Dict[str, int]:
        """Import a media archive file."""
        checksums_handles = self._identify_missing_files()

        if not checksums_handles:
            # no missing files
            # delete ZIP file
            if self.delete:
                self._delete_zip_file()
            return {"missing": 0, "uploaded": 0, "failures": 0}

        temp_dir = self._check_disk_space_and_extract()

        # delete ZIP file
        if self.delete:
            self._delete_zip_file()

        to_upload = self._identify_files_to_upload(temp_dir, checksums_handles)

        if not to_upload:
            # no files to upload
            self._delete_temporary_directory(temp_dir)
            return {"missing": len(checksums_handles), "uploaded": 0, "failures": 0}

        upload_size = sum(file_size for (_, file_size) in to_upload.values())
        check_quota_media(to_add=upload_size, tree=self.tree)

        num_failures = self._upload_files(to_upload, checksums_handles)

        self._delete_temporary_directory(temp_dir)
        self._update_media_usage()

        return {
            "missing": len(checksums_handles),
            "uploaded": len(to_upload) - num_failures,
            "failures": num_failures,
        }
