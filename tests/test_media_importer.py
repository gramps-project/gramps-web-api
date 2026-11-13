#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for the MediaImporter class."""

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Media

from gramps_webapi.api.file import get_checksum
from gramps_webapi.api.media import get_media_handler
from gramps_webapi.api.media_importer import (
    MAX_NOT_FOUND_LISTED,
    MediaImporter,
    match_members_to_paths,
)
from gramps_webapi.api.resources.util import add_object
from gramps_webapi.app import create_app
from gramps_webapi.auth import user_db
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager

ZIP_NAME = "file.zip"


def create_zip(names, temp_dir, delete_files: bool = False) -> List[str]:
    """Create a ZIP with random files and return a list of checksums."""
    checksums = []
    with zipfile.ZipFile(os.path.join(temp_dir, ZIP_NAME), "w") as fzip:
        for filename in names:
            path = os.path.join(temp_dir, filename)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(os.urandom(1000))
            with open(path, "rb") as f:
                checksums.append(get_checksum(f))
            fzip.write(path, filename)
            if delete_files:
                os.remove(path)
    return checksums


def counts(result) -> tuple[int, int, int]:
    """Return the missing, uploaded and failed counts of a result."""
    return result["missing"], result["uploaded"], result["failures"]


def not_found_paths(result) -> set[str]:
    """Return the paths of the media objects whose file was not found."""
    return {obj["path"] for obj in result["not_found"]}


def create_media(db_handle, file_paths, checksums):
    with DbTxn("Create media objects", db_handle) as trans:
        for file_path, checksum in zip(file_paths, checksums):
            obj = Media()
            obj.set_path(file_path)
            obj.set_checksum(checksum)
            add_object(db_handle, obj, trans)


@pytest.fixture
def setup():
    name = "Test MediaImporter"
    dbman = CLIDbManager(DbState())
    dirpath, _name = dbman.create_new_db_cli(name, dbid="sqlite")
    tree = os.path.basename(dirpath)
    temp_dir = tempfile.mkdtemp()
    media_dir = os.path.join(temp_dir, "media")
    os.mkdir(media_dir)
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
        app = create_app(
            config={
                "TESTING": True,
                "RATELIMIT_ENABLED": False,
                "MEDIA_BASE_DIR": media_dir,
            }
        )
    with app.app_context():
        user_db.create_all()
        dbmgr = WebDbManager(name)
        db_handle = dbmgr.get_db(readonly=False).db
        yield tree, db_handle, temp_dir
    db_handle.close(update=False)
    dbman.remove_database(name)
    shutil.rmtree(temp_dir)


def test_no_media(setup):
    """Test without media objects.

    Nothing to do."""
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg"]
    create_zip(files, temp_dir)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert result == {"missing": 0, "uploaded": 0, "failures": 0, "not_found": []}


def test_two_files(setup):
    """Test with two files and the corresponding media objects.

    Two missing files to be uploaded."""
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir)
    create_media(db_handle, files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert counts(result) == (2, 2, 0)
    assert result["not_found"] == []


def test_wrong_checksums(setup):
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir)
    wrong_checksums = [cs + "xx" for cs in checksums]
    create_media(db_handle, files, wrong_checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert counts(result) == (2, 0, 0)
    assert not_found_paths(result) == {"f1.jpg", "subfolder/f2.jpg"}


def test_wrong_filenames(setup):
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir)
    wrong_files = ["xx" + fn for fn in files]
    create_media(db_handle, wrong_files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert counts(result) == (2, 2, 0)
    assert result["not_found"] == []


def test_empty_checksums(setup):
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir)
    checksums = ["", ""]
    create_media(db_handle, files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert counts(result) == (2, 2, 0)
    assert result["not_found"] == []


def test_mixed(setup):
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg", "subfolder/subsub/f3.jpg"]
    checksums = create_zip(files, temp_dir)
    # one correct, one empty, two wrong checksums
    checksums = [checksums[0], "", "wrong", "whatever"]
    files = files + ["doesntexist.jpg"]
    create_media(db_handle, files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert counts(result) == (4, 2, 0)
    # a wrong checksum is not fixed by matching the path
    assert not_found_paths(result) == {"subfolder/subsub/f3.jpg", "doesntexist.jpg"}


def test_quota_checked_before_extraction(setup):
    """The quota must be checked before anything is written to disk."""
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir, delete_files=True)
    create_media(db_handle, files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name, delete=False)
    with patch.object(
        MediaImporter, "_extract_files", side_effect=AssertionError("extracted")
    ):
        with patch(
            "gramps_webapi.api.media_importer.check_quota_media",
            side_effect=ValueError("quota exceeded"),
        ) as check_quota:
            with pytest.raises(ValueError, match="quota exceeded"):
                mi()
    # the quota is checked for the size of the files to be uploaded only
    assert check_quota.call_args.kwargs["to_add"] == 2000


def test_only_missing_files_extracted(setup):
    """Only the ZIP members that are actually needed are extracted."""
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir, delete_files=True)
    # only the first file has a media object, so only it needs to be extracted
    create_media(db_handle, files[:1], checksums[:1])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name, delete=False)
    # enough space for one of the two files, but not for both
    usage = shutil.disk_usage(temp_dir)._replace(free=1500)
    with patch("shutil.disk_usage", return_value=usage):
        result = mi()
    assert counts(result) == (1, 1, 0)


def test_not_enough_disk_space(setup):
    """Extraction is refused if the temporary file system is too small."""
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir, delete_files=True)
    create_media(db_handle, files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name, delete=False)
    usage = shutil.disk_usage(temp_dir)._replace(free=1500)
    with patch("shutil.disk_usage", return_value=usage):
        with pytest.raises(ValueError, match="Not enough free space"):
            mi()


def test_zip_file_deleted_on_error(setup):
    """The ZIP file is deleted even if the import fails."""
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg"]
    checksums = create_zip(files, temp_dir, delete_files=True)
    create_media(db_handle, files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name, delete=True)
    with patch.object(MediaImporter, "_upload_files", side_effect=ValueError("boom")):
        with pytest.raises(ValueError, match="boom"):
            mi()
    assert not os.path.exists(zip_file_name)


def get_media_by_id(db_handle, gramps_id: str) -> Media:
    """Return the media object with a Gramps ID."""
    return db_handle.get_media_from_gramps_id(gramps_id)


def media_dir(temp_dir: str) -> str:
    """Return the media base directory of the `setup` fixture."""
    return os.path.join(temp_dir, "media")


@pytest.mark.parametrize(
    "original_path",
    [
        r"C:\Users\Anna\Pictures\Family\grandpa.jpg",
        "/Users/anna/Pictures/Family/grandpa.jpg",
        r"C:\Users\Anna\Pictures\Family\GRANDPA.JPG",
    ],
)
def test_file_name_fallback(setup, original_path):
    """A file is matched by its name, and the media path set to the ZIP's."""
    tree, db_handle, temp_dir = setup
    files = ["Family/grandpa.jpg"]
    checksums = create_zip(files, temp_dir)
    create_media(db_handle, [original_path], [""])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    result = MediaImporter(tree, "uid", db_handle, zip_file_name)()
    assert counts(result) == (1, 1, 0)
    assert result["not_found"] == []
    obj = get_media_by_id(db_handle, "O0000")
    assert obj.get_path() == "Family/grandpa.jpg"
    assert obj.get_checksum() == checksums[0]
    assert os.path.isfile(os.path.join(media_dir(temp_dir), "Family", "grandpa.jpg"))


def test_file_name_fallback_ambiguous_paths(setup):
    """Two media paths with the same file name are not matched by name."""
    tree, db_handle, temp_dir = setup
    create_zip(["Dad/photo.jpg", "Mum/photo.jpg"], temp_dir)
    paths = [r"C:\Pictures\Dad\photo.jpg", r"C:\Pictures\Mum\photo.jpg"]
    create_media(db_handle, paths, ["", ""])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    result = MediaImporter(tree, "uid", db_handle, zip_file_name)()
    assert counts(result) == (2, 0, 0)
    assert not_found_paths(result) == set(paths)
    assert get_media_by_id(db_handle, "O0000").get_path() == paths[0]


def test_file_name_fallback_ambiguous_members(setup):
    """A file name occurring twice in the ZIP is not matched by name."""
    tree, db_handle, temp_dir = setup
    create_zip(["Dad/photo.jpg", "Mum/photo.jpg"], temp_dir)
    create_media(db_handle, [r"C:\Pictures\photo.jpg"], [""])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    result = MediaImporter(tree, "uid", db_handle, zip_file_name)()
    assert counts(result) == (1, 0, 0)
    assert not_found_paths(result) == {r"C:\Pictures\photo.jpg"}


def test_same_path_shared_by_objects(setup):
    """Media objects sharing a path all get the file matched by name."""
    tree, db_handle, temp_dir = setup
    create_zip(["photo.jpg"], temp_dir)
    path = r"C:\Pictures\photo.jpg"
    create_media(db_handle, [path, path], ["", ""])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    result = MediaImporter(tree, "uid", db_handle, zip_file_name)()
    assert counts(result) == (2, 2, 0)
    for gramps_id in ["O0000", "O0001"]:
        assert get_media_by_id(db_handle, gramps_id).get_path() == "photo.jpg"


def test_unmatched_empty_checksums_counted(setup):
    """Objects without checksum and file each count, and are listed."""
    tree, db_handle, temp_dir = setup
    create_zip(["f1.jpg"], temp_dir)
    paths = ["f1.jpg", "a.jpg", "b.jpg", "c.jpg"]
    create_media(db_handle, paths, ["", "", "", ""])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    result = MediaImporter(tree, "uid", db_handle, zip_file_name)()
    assert counts(result) == (4, 1, 0)
    assert not_found_paths(result) == {"a.jpg", "b.jpg", "c.jpg"}
    assert {obj["gramps_id"] for obj in result["not_found"]} == {
        "O0001",
        "O0002",
        "O0003",
    }


def test_not_found_list_is_capped(setup):
    """The list of objects whose file was not found is bounded."""
    tree, db_handle, temp_dir = setup
    create_zip(["f1.jpg"], temp_dir)
    num = MAX_NOT_FOUND_LISTED + 5
    create_media(db_handle, [f"{i}.jpg" for i in range(num)], ["x"] * num)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    result = MediaImporter(tree, "uid", db_handle, zip_file_name)()
    assert counts(result) == (num, 0, 0)
    assert len(result["not_found"]) == MAX_NOT_FOUND_LISTED


def test_match_exact_path():
    """A member with the media path matches."""
    assert match_members_to_paths(["a/b.jpg"], ["a/b.jpg", "b.jpg"]) == {
        "a/b.jpg": "a/b.jpg"
    }


def test_match_exact_path_takes_its_member_out_of_the_fallback():
    """A member matched exactly is not also matched by file name."""
    matches = match_members_to_paths(["a/b.jpg", r"C:\x\b.jpg"], ["a/b.jpg"])
    assert matches == {"a/b.jpg": "a/b.jpg"}


def test_match_file_name():
    """Windows and POSIX paths match by file name, ignoring case."""
    matches = match_members_to_paths(
        [r"C:\x\One.JPG", "/home/x/two.jpg"], ["pics/one.jpg", "two.jpg"]
    )
    assert matches == {r"C:\x\One.JPG": "pics/one.jpg", "/home/x/two.jpg": "two.jpg"}


def test_match_unsafe_member_names():
    """Members that would end up outside the media folder never match by name."""
    members = ["../evil.jpg", "/abs/evil2.jpg", "C:/evil3.jpg"]
    paths = [r"C:\x\evil.jpg", r"C:\x\evil2.jpg", r"C:\x\evil3.jpg"]
    assert match_members_to_paths(paths, members) == {}


def test_match_double_slash_member():
    """A member with a double-slash absolute path never matches by name."""
    assert match_members_to_paths([r"C:\x\photo.jpg"], ["//outside/photo.jpg"]) == {}


def test_file_name_fallback_existing_different_file(setup):
    """A different file already at the ZIP member's path is not overwritten."""
    tree, db_handle, temp_dir = setup
    create_zip(["photo.jpg"], temp_dir)
    existing = os.path.join(media_dir(temp_dir), "photo.jpg")
    with open(existing, "wb") as f:
        f.write(b"someone else's photo")
    path = r"C:\Pictures\photo.jpg"
    create_media(db_handle, [path], [""])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert counts(result) == (1, 0, 0)
    assert not_found_paths(result) == {path}
    obj = get_media_by_id(db_handle, "O0000")
    assert obj.get_path() == path
    assert obj.get_checksum() == ""
    assert not mi.paths_changed
    with open(existing, "rb") as f:
        assert f.read() == b"someone else's photo"


def test_file_name_fallback_existing_same_file(setup):
    """The same file already at the ZIP member's path is linked."""
    tree, db_handle, temp_dir = setup
    checksums = create_zip(["photo.jpg"], temp_dir)
    shutil.copy(
        os.path.join(temp_dir, "photo.jpg"),
        os.path.join(media_dir(temp_dir), "photo.jpg"),
    )
    create_media(db_handle, [r"C:\Pictures\photo.jpg"], [""])
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    mi()
    obj = get_media_by_id(db_handle, "O0000")
    assert obj.get_path() == "photo.jpg"
    assert obj.get_checksum() == checksums[0]
    assert mi.paths_changed


def test_archive_not_read_without_checksums_to_find(setup):
    """Without missing media objects, the archive is not hashed."""
    tree, db_handle, temp_dir = setup
    create_zip(["f1.jpg"], temp_dir)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    with patch.object(
        MediaImporter,
        "_identify_files_to_upload",
        side_effect=AssertionError("archive read"),
    ):
        result = mi()
    assert counts(result) == (0, 0, 0)
