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

    def _extract_files(
        self, to_upload: Dict[str, Tuple[str, int]]
    ) -> Tuple[str, Dict[str, Tuple[str, int]]]:
        """Extract the members to be uploaded into a temporary directory.

        Only the members that are actually needed are extracted, and only if
        the file system holding the temporary directory has room for them.
        Returns the temporary directory and a dictionary mapping checksums to
        the extracted file path and size.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            temp_dir_real = os.path.realpath(temp_dir)
            total_size = sum(file_size for (_, file_size) in to_upload.values())
            if total_size > shutil.disk_usage(temp_dir_real).free:
                raise ValueError("Not enough free space on disk")

            extracted: Dict[str, Tuple[str, int]] = {}
            with zipfile.ZipFile(self.file_name, "r") as zip_file:
                for checksum, (member, file_size) in to_upload.items():
                    member_path = os.path.realpath(os.path.join(temp_dir_real, member))
                    if not member_path.startswith(temp_dir_real + os.sep):
                        raise ValueError(f"Zip Slip path traversal detected: {member}")
                    file_path = zip_file.extract(member, temp_dir)
                    extracted[checksum] = (file_path, file_size)
        except Exception:
            self._delete_temporary_directory(temp_dir)
            raise

        return temp_dir, extracted

    def _fix_missing_checksums(self, missing_files: MissingFiles) -> int:
        """Fix objects with missing checksums if we have a file with matching path."""
        handles_by_path: Dict[str, List[str]] = {}
        for obj_details in missing_files[""]:
            path = obj_details["media_path"]
            if path not in handles_by_path:
                handles_by_path[path] = []
            handles_by_path[path].append(obj_details["handle"])
        checksums_by_handle: Dict[str, str] = {}
        with zipfile.ZipFile(self.file_name, "r") as zip_file:
            for file_info in zip_file.infolist():
                if file_info.is_dir() or file_info.filename not in handles_by_path:
                    continue
                with zip_file.open(file_info, "r") as f:
                    checksum = get_checksum(f)
                for handle in handles_by_path[file_info.filename]:
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
        self, missing_files: MissingFiles
    ) -> Dict[str, Tuple[str, int]]:
        """Identify the ZIP members to upload, keyed by checksum.

        The archive is read as a stream, so nothing is written to disk yet.
        Returns a dictionary mapping checksums to the member name and its
        uncompressed size.
        """
        to_upload: Dict[str, Tuple[str, int]] = {}
        with zipfile.ZipFile(self.file_name, "r") as zip_file:
            for file_info in zip_file.infolist():
                if file_info.is_dir():
                    continue
                with zip_file.open(file_info, "r") as f:
                    checksum = get_checksum(f)
                if checksum in missing_files and checksum not in to_upload:
                    to_upload[checksum] = (file_info.filename, file_info.file_size)

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
        """Delete the ZIP file, if it still exists."""
        try:
            os.remove(self.file_name)
        except FileNotFoundError:
            pass

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
        try:
            return self._import(
                fix_missing_checksums=fix_missing_checksums, progress_cb=progress_cb
            )
        finally:
            if self.delete:
                self._delete_zip_file()

    def _import(
        self, fix_missing_checksums: bool = True, progress_cb: Optional[Callable] = None
    ) -> Dict[str, int]:
        """Import a media archive file.

        The ZIP file is deleted as soon as it is no longer needed; `__call__`
        makes sure it is deleted as well if this method raises.
        """
        missing_files = self._identify_missing_files()

        if not missing_files:
            # no missing files
            return {"missing": 0, "uploaded": 0, "failures": 0}

        if "" in missing_files:
            if fix_missing_checksums:
                # files without checksum! Need to fix that first
                fixed = self._fix_missing_checksums(missing_files)
                # after fixing checksums, we need fetch media objects again and re-run
                if fixed:
                    self._update_objects()
                    # set fix_missing_checksums to False to avoid an infinite loop
                    return self._import(
                        fix_missing_checksums=False, progress_cb=progress_cb
                    )
            else:
                # we already tried fixing checksums - ignore the 2nd time
                missing_files.pop("")

        to_upload = self._identify_files_to_upload(missing_files)

        if not to_upload:
            # no files to upload
            return {"missing": len(missing_files), "uploaded": 0, "failures": 0}

        # check the quota before writing anything to disk
        upload_size = sum(file_size for (_, file_size) in to_upload.values())
        check_quota_media(to_add=upload_size, tree=self.tree, user_id=self.user_id)

        temp_dir, extracted = self._extract_files(to_upload)

        # the ZIP file is no longer needed - free the disk space it uses
        if self.delete:
            self._delete_zip_file()

        try:
            num_failures = self._upload_files(
                extracted, missing_files, progress_cb=progress_cb
            )
        finally:
            self._delete_temporary_directory(temp_dir)

        self._update_media_usage()

        return {
            "missing": len(missing_files),
            "uploaded": len(to_upload) - num_failures,
            "failures": num_failures,
        }


# _identify_missing_files -> missing_files = {checksum: [(handle, media_path, mime), ...]}
# _identify_files_to_upload -> to_upload = {checksum: (file_path, file_size)}
