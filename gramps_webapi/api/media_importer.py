"""Class for handling the import of a media ZIP archive."""

import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Tuple

from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import Media

from ..auth import set_tree_usage
from ..types import FilenameOrPath
from .file import get_checksum
from .media import check_quota_media, get_media_handler
from .resources.util import update_object

MissingFiles = Dict[str, List[Dict[str, str]]]

# media objects listed by name in the result when their file was not found;
# the result ends up in the task result backend, so its size must be bounded
MAX_NOT_FOUND_LISTED = 1000


def _file_name(path: str) -> str:
    """Return the last component of a path, ignoring case.

    Both separators are accepted, since media paths imported from other
    programs are often Windows paths.
    """
    return path.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _is_safe_relative_path(path: str) -> bool:
    """Whether a ZIP member name can serve as a path inside the media folder."""
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return bool(parts) and parts[0] != "/" and ".." not in parts and ":" not in path


def match_members_to_paths(
    paths: Iterable[str], members: Iterable[str]
) -> Dict[str, str]:
    """Map media paths to the names of the ZIP members holding their files.

    A member matches a path if its name equals the path. Failing that, it
    matches if the two have the same file name, ignoring case, and that file
    name occurs only once among the members and once among the paths not
    matched so far - otherwise there is no telling which file is which.
    """
    paths = list(paths)
    members = list(members)
    member_set = set(members)
    matches = {path: path for path in paths if path in member_set}
    used = set(matches.values())
    members_by_name: Dict[str, List[str]] = {}
    for member in members:
        if member not in used and _is_safe_relative_path(member):
            members_by_name.setdefault(_file_name(member), []).append(member)
    paths_by_name: Dict[str, List[str]] = {}
    for path in paths:
        if path not in matches:
            paths_by_name.setdefault(_file_name(path), []).append(path)
    for name, unmatched in paths_by_name.items():
        candidates = members_by_name.get(name, [])
        if name and len(unmatched) == 1 and len(candidates) == 1:
            matches[unmatched[0]] = candidates[0]
    return matches


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
      a file with the right (relative) path, or failing that, with the same file
      name (see `match_members_to_paths`). If one is found, the media object is
      updated with that file's checksum. If it was found by file name only, the
      object's path is also set to the file's path in the ZIP: the original path,
      often an absolute one from another computer, cannot be used on the server.
      Then, in a second step, the file is uploaded.

    The result counts media objects: those without a file before the import
    (`missing`), those whose file was uploaded (`uploaded`) and those whose
    upload failed (`failures`). The others, for which the ZIP held no file, are
    listed in `not_found`, up to `MAX_NOT_FOUND_LISTED` of them.
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
                "gramps_id": obj.gramps_id,
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
        """Fix objects with missing checksums if we have a matching file.

        See `match_members_to_paths` for which file matches. Returns the number
        of media objects updated.
        """
        handles_by_path: Dict[str, List[str]] = {}
        for obj_details in missing_files[""]:
            path = obj_details["media_path"]
            handles_by_path.setdefault(path, []).append(obj_details["handle"])
        with zipfile.ZipFile(self.file_name, "r") as zip_file:
            members = [info for info in zip_file.infolist() if not info.is_dir()]
            member_by_path = match_members_to_paths(
                handles_by_path, (info.filename for info in members)
            )
            checksums_by_member: Dict[str, str] = {}
            for file_info in members:
                if file_info.filename not in member_by_path.values():
                    continue
                with zip_file.open(file_info, "r") as f:
                    checksums_by_member[file_info.filename] = get_checksum(f)
        if not member_by_path:
            return 0
        objects_by_handle = {obj.handle: obj for obj in self.objects}
        num_updated = 0
        with DbTxn("Updating checksums on media", self.db_handle) as trans:
            for path, member in member_by_path.items():
                for handle in handles_by_path[path]:
                    new_object = objects_by_handle[handle]
                    new_object.set_checksum(checksums_by_member[member])
                    if member != path:
                        new_object.set_path(member)
                    update_object(self.db_handle, new_object, trans)
                    num_updated += 1

        return num_updated

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

    @staticmethod
    def _result(
        missing_files: MissingFiles,
        to_upload: Dict[str, Tuple[str, int]],
        num_failures: int,
    ) -> Dict[str, Any]:
        """Summarize the import, counting media objects."""
        num_missing = sum(len(objects) for objects in missing_files.values())
        num_to_upload = sum(len(missing_files[checksum]) for checksum in to_upload)
        not_found = [
            {
                "handle": obj_details["handle"],
                "gramps_id": obj_details["gramps_id"],
                "path": obj_details["media_path"],
            }
            for checksum, objects in missing_files.items()
            if checksum not in to_upload
            for obj_details in objects
        ]
        return {
            "missing": num_missing,
            "uploaded": num_to_upload - num_failures,
            "failures": num_failures,
            "not_found": not_found[:MAX_NOT_FOUND_LISTED],
        }

    def __call__(
        self, fix_missing_checksums: bool = True, progress_cb: Optional[Callable] = None
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """Import a media archive file.

        The ZIP file is deleted as soon as it is no longer needed; `__call__`
        makes sure it is deleted as well if this method raises.
        """
        missing_files = self._identify_missing_files()

        if "" in missing_files and fix_missing_checksums:
            # files without checksum! Need to fix that first
            fixed = self._fix_missing_checksums(missing_files)
            # after fixing checksums, we need fetch media objects again and re-run
            if fixed:
                self._update_objects()
                # set fix_missing_checksums to False to avoid an infinite loop
                return self._import(
                    fix_missing_checksums=False, progress_cb=progress_cb
                )

        # objects still without checksum have no file in the ZIP
        to_upload = self._identify_files_to_upload(
            {checksum: objs for checksum, objs in missing_files.items() if checksum}
        )

        if not to_upload:
            # no files to upload
            return self._result(missing_files, to_upload, num_failures=0)

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

        return self._result(missing_files, to_upload, num_failures=num_failures)


# _identify_missing_files -> missing_files = {checksum: [(handle, media_path, mime), ...]}
# _identify_files_to_upload -> to_upload = {checksum: (file_path, file_size)}
