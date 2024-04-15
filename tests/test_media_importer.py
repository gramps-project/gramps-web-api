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
from gramps_webapi.api.media_importer import MediaImporter
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
    assert result == {"missing": 0, "uploaded": 0, "failures": 0}


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
    assert result == {"missing": 2, "uploaded": 2, "failures": 0}


def test_wrong_checksums(setup):
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir)
    wrong_checksums = [cs + "xx" for cs in checksums]
    create_media(db_handle, files, wrong_checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert result == {"missing": 2, "uploaded": 0, "failures": 0}


def test_wrong_filenames(setup):
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir)
    wrong_files = ["xx" + fn for fn in files]
    create_media(db_handle, wrong_files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert result == {"missing": 2, "uploaded": 2, "failures": 0}


def test_empty_checksums(setup):
    tree, db_handle, temp_dir = setup
    files = ["f1.jpg", "subfolder/f2.jpg"]
    checksums = create_zip(files, temp_dir)
    checksums = ["", ""]
    create_media(db_handle, files, checksums)
    zip_file_name = os.path.join(temp_dir, ZIP_NAME)
    mi = MediaImporter(tree, "uid", db_handle, zip_file_name)
    result = mi()
    assert result == {"missing": 2, "uploaded": 2, "failures": 0}


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
    assert result == {"missing": 4, "uploaded": 2, "failures": 0}
