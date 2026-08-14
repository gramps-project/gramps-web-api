#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Tests for media endpoints when the tree-prefixed media folder is missing."""

import io
import os
import shutil
import tempfile
import zipfile
from unittest.mock import patch

import pytest
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Media

from gramps_webapi.api.file import get_checksum
from gramps_webapi.api.resources.util import add_object
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager

DB_NAME = "Test MediaPrefixTree"
FILE_CONTENT = b"not really a JPEG, but nobody looks"
FILE_NAME = "f1.jpg"


@pytest.fixture
def setup():
    """Set up a tree whose prefixed media folder has never been created.

    This is the state of a freshly created tree in a multi-tree install: media
    objects can already exist (e.g. from an import) while no file has ever been
    uploaded, so `MEDIA_BASE_DIR/<tree>` does not exist yet.
    """
    dbman = CLIDbManager(DbState())
    dirpath, _name = dbman.create_new_db_cli(DB_NAME, dbid="sqlite")
    tree = os.path.basename(dirpath)
    temp_dir = tempfile.mkdtemp()
    media_dir = os.path.join(temp_dir, "media")
    os.mkdir(media_dir)
    export_dir = os.path.join(temp_dir, "export")
    os.mkdir(export_dir)
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
        app = create_app(
            config={
                "TESTING": True,
                "RATELIMIT_ENABLED": False,
                "MEDIA_BASE_DIR": media_dir,
                "MEDIA_PREFIX_TREE": True,
                "EXPORT_DIR": export_dir,
                "TREE": DB_NAME,
            },
            config_from_env=False,
        )
    with app.app_context():
        user_db.create_all()
        add_user(name="owner", password="owner", role=ROLE_OWNER, tree=tree)
        db_handle = WebDbManager(DB_NAME).get_db(readonly=False).db
        with DbTxn("Add media object", db_handle) as trans:
            obj = Media()
            obj.set_path(FILE_NAME)
            obj.set_checksum(get_checksum(io.BytesIO(FILE_CONTENT)))
            obj.set_mime_type("image/jpeg")
            add_object(db_handle, obj, trans)
            handle = obj.handle
        db_handle.close()
    prefixed_dir = os.path.join(media_dir, tree)
    assert not os.path.isdir(prefixed_dir)
    yield app.test_client(), handle, prefixed_dir
    dbman.remove_database(DB_NAME)
    shutil.rmtree(temp_dir)


def get_headers(client):
    """Get the auth headers for the owner."""
    rv = client.post("/api/token/", json={"username": "owner", "password": "owner"})
    return {"Authorization": "Bearer {}".format(rv.json["access_token"])}


def test_upload_missing_file(setup):
    """The first upload must create the prefixed folder rather than fail."""
    client, handle, prefixed_dir = setup
    headers = get_headers(client)
    rv = client.get(f"/api/media/{handle}/file", headers=headers)
    assert rv.status_code == 404
    rv = client.get("/api/media/?filemissing=1", headers=headers)
    assert rv.status_code == 200
    assert len(rv.json) == 1
    rv = client.put(
        f"/api/media/{handle}/file?uploadmissing=1",
        data=FILE_CONTENT,
        headers=headers,
        content_type="image/jpeg",
    )
    assert rv.status_code == 200
    assert os.path.isfile(os.path.join(prefixed_dir, FILE_NAME))
    rv = client.get(f"/api/media/{handle}/file", headers=headers)
    assert rv.status_code == 200
    assert rv.data == FILE_CONTENT


def test_create_archive(setup):
    """Archiving a tree without a prefixed folder must yield an empty archive."""
    client, _handle, _prefixed_dir = setup
    headers = get_headers(client)
    rv = client.post("/api/media/archive/", headers=headers)
    assert rv.status_code == 201, rv.json
    rv = client.get(rv.json["url"], headers=headers)
    assert rv.status_code == 200
    with zipfile.ZipFile(io.BytesIO(rv.data)) as zip_file:
        assert zip_file.namelist() == []
