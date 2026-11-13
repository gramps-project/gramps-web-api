"""Class for handling the import of a media ZIP archive."""

import os
import shutil
import tempfile
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import Media

from ..auth import set_tree_usage
from ..types import FilenameOrPath
from .file import get_checksum
from .media import (
    MediaHandlerLocal,
    check_quota_media,
    get_contained_path,
    get_media_handler,
)
from .resources.util import update_object

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
    posix_path = PurePosixPath(path.replace("\\", "/"))
    return (
        bool(posix_path.parts)
        and not posix_path.is_absolute()
        and ".." not in posix_path.parts
        and ":" not in path
    )


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


@dataclass
class _Match:
    """A media object without a file, and the ZIP member holding it."""

    obj: Media
    member: str
    checksum: str
    # where the file is stored: the object's path after the import
    path: str
    # whether the path differs from the object's current one
    renamed: bool
    # whether the file is already stored, so only the object needs updating
    present: bool = False


class MediaImporter:
    """A class to handle a media archiv ZIP file and import media files.

    The class takes a tree ID, database handle, and ZIP file path as input.
    If delete is true (the default), the ZIP file is deleted when the import
    is done.

    The import looks at the media objects whose file is missing (for local
    storage, no file at the object's path; for object storage, no object with
    the object's checksum as key) and goes through these steps:

    1. Plan: find the ZIP member holding each object's file.

       - An object with a checksum matches a member with that checksum,
         regardless of its name.
       - An object without a checksum matches a member whose name equals the
         object's path or, failing that, has the same file name (see
         `match_members_to_paths`). If it was found by file name only, the
         object's path is set to the member's: the original path, often an
         absolute one from another computer, cannot be used on the server.

       With local storage, a match by file name is dropped if a different
       file is stored at the member's path already, or another match is
       going to store a different file there.
    2. Check the quota, extract the needed members and upload them (local
       storage stores them at the object's path, object storage by checksum).
    3. Set the checksums and paths of the objects whose file is now stored,
       in a single transaction.

    Nothing is changed in the database if a step before the last one fails.

    The result counts media objects: those without a file before the import
    (`missing`), those whose file is now stored (`uploaded`) and those whose
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
        # whether the import changed the path of any media object
        self.paths_changed = False

    def _identify_missing_objects(self) -> List[Media]:
        """Return the media objects whose file is missing."""
        objects = list(self.db_handle.iter_media())
        handles_existing = {
            obj.handle
            for obj in self.media_handler.filter_existing_files(
                objects, db_handle=self.db_handle
            )
        }
        return [obj for obj in objects if obj.handle not in handles_existing]

    def _match_archive(
        self, missing: List[Media]
    ) -> Tuple[List[_Match], Dict[str, int]]:
        """Find the ZIP member holding the file of each missing object.

        The archive is read as a stream, so nothing is written to disk yet.
        Members are only hashed if they can match. A name occurring more than
        once in the archive is ambiguous, so its members are ignored. Returns
        the matches and the uncompressed sizes of the members, by name.
        """
        without_checksum: Dict[str, List[Media]] = {}
        for obj in missing:
            if not obj.checksum:
                without_checksum.setdefault(obj.get_path(), []).append(obj)
        with zipfile.ZipFile(self.file_name, "r") as zip_file:
            files = [info for info in zip_file.infolist() if not info.is_dir()]
            name_counts = Counter(info.filename for info in files)
            infos = {
                info.filename: info for info in files if name_counts[info.filename] == 1
            }
            member_by_path = match_members_to_paths(without_checksum, infos)
            if any(obj.checksum for obj in missing):
                # some objects can match any member by checksum
                to_hash: Iterable[str] = infos
            else:
                to_hash = set(member_by_path.values())
            checksums: Dict[str, str] = {}
            for name in to_hash:
                with zip_file.open(infos[name], "r") as f:
                    checksums[name] = get_checksum(f)
        member_by_checksum: Dict[str, str] = {}
        for name, checksum in checksums.items():
            member_by_checksum.setdefault(checksum, name)
        matches: List[_Match] = []
        for obj in missing:
            if obj.checksum:
                member = member_by_checksum.get(obj.checksum)
                if member is not None:
                    matches.append(
                        _Match(obj, member, obj.checksum, obj.get_path(), False)
                    )
                continue
            member = member_by_path.get(obj.get_path())
            if member is not None:
                renamed = member != obj.get_path()
                matches.append(_Match(obj, member, checksums[member], member, renamed))
        sizes = {name: info.file_size for name, info in infos.items()}
        return matches, sizes

    def _drop_conflicts(self, matches: List[_Match]) -> List[_Match]:
        """Drop matches by file name whose path is taken by a different file.

        The path is taken if a file with a different checksum is stored there
        already, or another match is going to store one there. If the same
        file is stored there already, the match is kept and marked present.

        Only local storage keeps files by path; object storage keeps them by
        checksum, so there can be no conflict.
        """
        if not isinstance(self.media_handler, MediaHandlerLocal):
            return matches
        base_dir = self.media_handler.base_dir
        destinations = [get_contained_path(base_dir, m.path) for m in matches]
        checksums_by_destination: Dict[Optional[Path], Set[str]] = {}
        for match, destination in zip(matches, destinations):
            checksums_by_destination.setdefault(destination, set()).add(match.checksum)
        kept = []
        for match, destination in zip(matches, destinations):
            if match.renamed:
                if destination is None:
                    continue
                if len(checksums_by_destination[destination]) > 1:
                    continue
                if destination.exists():
                    if not destination.is_file():
                        continue
                    with open(destination, "rb") as f:
                        if get_checksum(f) != match.checksum:
                            continue
                    match.present = True
            kept.append(match)
        return kept

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

    def _upload_files(
        self,
        matches: List[_Match],
        extracted: Dict[str, Tuple[str, int]],
        progress_cb: Optional[Callable] = None,
    ) -> Set[str]:
        """Upload the files of the matches and return the handles that failed."""
        failed: Set[str] = set()
        total = len(matches)
        for i, match in enumerate(matches):
            if progress_cb:
                progress_cb(current=i, total=total)
            file_path, _ = extracted[match.checksum]
            with open(file_path, "rb") as f:
                try:
                    self.media_handler.upload_file(
                        f, match.checksum, match.obj.get_mime_type(), path=match.path
                    )
                except Exception:
                    failed.add(match.obj.handle)
        return failed

    def _commit(self, matches: List[_Match]) -> None:
        """Set the checksums and paths of the matched objects."""
        changed = [
            match
            for match in matches
            if match.renamed or match.checksum != match.obj.checksum
        ]
        if not changed:
            return
        with DbTxn("Updating media from archive", self.db_handle) as trans:
            for match in changed:
                match.obj.set_checksum(match.checksum)
                if match.renamed:
                    match.obj.set_path(match.path)
                update_object(self.db_handle, match.obj, trans)
        if any(match.renamed for match in changed):
            self.paths_changed = True

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
        missing: List[Media], matches: List[_Match], failed: Set[str]
    ) -> Dict[str, Any]:
        """Summarize the import, counting media objects."""
        matched = {match.obj.handle for match in matches}
        not_found = [
            {"handle": obj.handle, "gramps_id": obj.gramps_id, "path": obj.get_path()}
            for obj in missing
            if obj.handle not in matched
        ]
        return {
            "missing": len(missing),
            "uploaded": len(matches) - len(failed),
            "failures": len(failed),
            "not_found": not_found[:MAX_NOT_FOUND_LISTED],
        }

    def __call__(self, progress_cb: Optional[Callable] = None) -> Dict[str, Any]:
        """Import a media archive file."""
        try:
            return self._import(progress_cb=progress_cb)
        finally:
            if self.delete:
                self._delete_zip_file()

    def _import(self, progress_cb: Optional[Callable] = None) -> Dict[str, Any]:
        """Import a media archive file.

        The ZIP file is deleted as soon as it is no longer needed; `__call__`
        makes sure it is deleted as well if this method raises.
        """
        missing = self._identify_missing_objects()
        if not missing:
            # nothing to look for - don't read the archive
            return self._result(missing, [], set())

        matches, sizes = self._match_archive(missing)
        matches = self._drop_conflicts(matches)

        to_store = [match for match in matches if not match.present]
        to_upload = {
            match.checksum: (match.member, sizes[match.member]) for match in to_store
        }
        failed: Set[str] = set()
        if to_upload:
            # check the quota before writing anything to disk
            upload_size = sum(file_size for (_, file_size) in to_upload.values())
            check_quota_media(to_add=upload_size, tree=self.tree, user_id=self.user_id)

            temp_dir, extracted = self._extract_files(to_upload)

            # the ZIP file is no longer needed - free the disk space it uses
            if self.delete:
                self._delete_zip_file()

            try:
                failed = self._upload_files(to_store, extracted, progress_cb)
            finally:
                self._delete_temporary_directory(temp_dir)

        stored = [match for match in matches if match.obj.handle not in failed]
        self._commit(stored)
        if stored:
            self._update_media_usage()

        return self._result(missing, matches, failed)
