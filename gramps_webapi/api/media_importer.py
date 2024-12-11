"""Class for handling the import of a media ZIP archive."""

import os
import shutil
import tempfile
import zipfile
from typing import Callable, Dict, List, Optional, Tuple

from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import Media

from ..auth import set_tree_usage
from ..types import FilenameOrPath
from .file import get_checksum
from .media import check_quota_media, get_media_handler
from .resources.util import update_object

MissingFiles = Dict[str, List[Dict[str, str]]]


class MediaImporter:
    """A class to handle a media archiv ZIP file and import media files.

    The class takes a tree ID, database handle, and ZIP file path as input.
    If delete is true (the default), the ZIP file is deleted when the import
    is done.

    The importer uses the following criteria:

    - For any media objects that have a checksum but where no file is found
      (for local file handler, this means no file is found at the respective path,
      for object storage, this means no object with that checksum as key is found),
      it looks for a file with the right checksum (regardless of filename) in the ZIP.
      If one is found, it is uploaded to the media storage (in the case of local file
      handler, it is renamed to the path in the media object; in the case of object
      storage, it is uploaded by checksum).
    - For any media objects that have an empty checksum (and, in the case of local file
      storage, do not have a file at the right path), the ZIP archive is searched for
      a file with the right (relative) path. If one is found, the media object is
      updated with that file's checksum. Then, in a second step, the file is uploaded.

    """

    def __init__(
        self,
        tree: str,
        user_id: str,
        db_handle: DbReadBase,
        file_name: FilenameOrPath,
        delete: bool = True,
    ) -> None:
        """Initialize media importer."""
        self.tree = tree
        self.user_id = user_id
        self.db_handle = db_handle
        self.file_name = file_name
        self.delete = delete
        self.media_handler = get_media_handler(self.db_handle, tree=self.tree)
        self.objects: List[Media] = self._get_objects()

    def _get_objects(self) -> List[Media]:
        """Get a list of all media objects in the database."""
        return list(self.db_handle.iter_media())

    def _update_objects(self) -> None:
        """Update the list of media objects."""
        self.objects = self._get_objects()

    def _identify_missing_files(self) -> MissingFiles:
        """Identify missing files by comparing existing handles with all media objects."""
        objects_existing = self.media_handler.filter_existing_files(
            self.objects, db_handle=self.db_handle
        )
        handles_existing = set(obj.handle for obj in objects_existing)
        objects_missing = [
            obj for obj in self.objects if obj.handle not in handles_existing
        ]

        missing_files: dict[str, list[dict[str, str]]] = {}
        for obj in objects_missing:
            if obj.checksum not in missing_files:
                missing_files[obj.checksum] = []
            obj_details = {
                "handle": obj.handle,
                "media_path": obj.get_path(),
                "mime": obj.get_mime_type(),
            }
            missing_files[obj.checksum].append(obj_details)

        return missing_files

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

    def _fix_missing_checksums(self, temp_dir: str, missing_files: MissingFiles) -> int:
        """Fix objects with missing checksums if we have a file with matching path."""
        handles_by_path: Dict[str, List[str]] = {}
        for obj_details in missing_files[""]:
            path = obj_details["media_path"]
            if path not in handles_by_path:
                handles_by_path[path] = []
            handles_by_path[path].append(obj_details["handle"])
        checksums_by_handle: Dict[str, str] = {}
        for root, _, files in os.walk(temp_dir):
            for name in files:
                abs_file_path = os.path.join(root, name)
                rel_file_path = os.path.relpath(abs_file_path, temp_dir)
                if rel_file_path in handles_by_path:
                    with open(abs_file_path, "rb") as f:
                        checksum = get_checksum(f)
                    for handle in handles_by_path[rel_file_path]:
                        checksums_by_handle[handle] = checksum
        if not checksums_by_handle:
            return 0
        with DbTxn("Updating checksums on media", self.db_handle) as trans:
            objects_by_handle = {
                obj.handle: obj
                for obj in self.objects
                if obj.handle in checksums_by_handle
            }
            for handle, checksum in checksums_by_handle.items():
                new_object = objects_by_handle[handle]
                new_object.set_checksum(checksum)
                update_object(self.db_handle, new_object, trans)

        return len(checksums_by_handle)

    def _identify_files_to_upload(
        self, temp_dir: str, missing_files: MissingFiles
    ) -> Dict[str, Tuple[str, int]]:
        """Identify files to upload from the extracted temporary directory."""
        to_upload = {}
        for root, _, files in os.walk(temp_dir):
            for name in files:
                file_path = os.path.join(root, name)
                with open(file_path, "rb") as f:
                    checksum = get_checksum(f)
                    if checksum in missing_files and checksum not in to_upload:
                        to_upload[checksum] = (file_path, os.path.getsize(file_path))

        return to_upload

    def _upload_files(
        self,
        to_upload: Dict[str, Tuple[str, int]],
        missing_files: MissingFiles,
        progress_cb: Optional[Callable] = None,
    ) -> int:
        """Upload identified files and return the number of failures."""
        num_failures = 0
        total = len(to_upload)
        for i, (checksum, (file_path, file_size)) in enumerate(to_upload.items()):
            if progress_cb:
                progress_cb(current=i, total=total)
            for obj_details in missing_files[checksum]:
                with open(file_path, "rb") as f:
                    try:
                        self.media_handler.upload_file(
                            f,
                            checksum,
                            obj_details["mime"],
                            path=obj_details["media_path"],
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

    def __call__(
        self, fix_missing_checksums: bool = True, progress_cb: Optional[Callable] = None
    ) -> Dict[str, int]:
        """Import a media archive file."""
        missing_files = self._identify_missing_files()

        if not missing_files:
            # no missing files
            # delete ZIP file
            if self.delete:
                self._delete_zip_file()
            return {"missing": 0, "uploaded": 0, "failures": 0}

        temp_dir = self._check_disk_space_and_extract()

        if "" in missing_files:
            if fix_missing_checksums:
                # files without checksum! Need to fix that first
                fixed = self._fix_missing_checksums(temp_dir, missing_files)
                # after fixing checksums, we need fetch media objects again and re-run
                if fixed:
                    self._update_objects()
                    # set fix_missing_checksums to False to avoid an infinite loop
                    return self(fix_missing_checksums=False)
            else:
                # we already tried fixing checksums - ignore the 2nd time
                missing_files.pop("")

        # delete ZIP file
        if self.delete:
            self._delete_zip_file()

        to_upload = self._identify_files_to_upload(temp_dir, missing_files)

        if not to_upload:
            # no files to upload
            self._delete_temporary_directory(temp_dir)
            return {"missing": len(missing_files), "uploaded": 0, "failures": 0}

        upload_size = sum(file_size for (_, file_size) in to_upload.values())
        check_quota_media(to_add=upload_size, tree=self.tree, user_id=self.user_id)

        num_failures = self._upload_files(
            to_upload, missing_files, progress_cb=progress_cb
        )

        self._delete_temporary_directory(temp_dir)
        self._update_media_usage()

        return {
            "missing": len(missing_files),
            "uploaded": len(to_upload) - num_failures,
            "failures": num_failures,
        }


# _identify_missing_files -> missing_files = {checksum: [(handle, media_path, mime), ...]}
# _identify_files_to_upload -> to_upload = {checksum: (file_path, file_size)}
