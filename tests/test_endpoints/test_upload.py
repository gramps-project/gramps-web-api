#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2022      David Straub
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

"""Tests uploading media files POST."""

import hashlib
import os
import shutil
import tempfile
import unittest
from io import BytesIO
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState
from PIL import Image

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_ADMIN, ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


def get_image(color, width=50, height=50):
    """Get a JPEG image and checksum."""
    image_file = BytesIO()
    image = Image.new("RGBA", size=(width, height), color=color)
    image.save(image_file, "png")
    image_file.seek(0)
    checksum = hashlib.md5(image_file.getbuffer()).hexdigest()
    image_file.read()
    size = image_file.tell()
    image_file.seek(0)
    return image_file, checksum, size


class TestUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.media_base_dir = tempfile.mkdtemp()
        cls.app.config["MEDIA_BASE_DIR"] = cls.media_base_dir
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        shutil.rmtree(cls.media_base_dir)

    def test_upload_new_media(self):
        """Add new media object."""
        img, checksum, size = get_image(0)
        # try as guest - not allowed
        headers = get_headers(self.client, "user", "123")
        rv = self.client.post(
            "/api/media/", data=None, headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 403)
        # try as admin
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        # check output
        out = rv.json
        self.assertEqual(len(out), 1)
        handle = out[0]["new"]["handle"]
        self.assertEqual(out[0]["old"], None)
        self.assertEqual(out[0]["type"], "add")
        # get the object
        rv = self.client.get(f"/api/media/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        res = rv.json
        self.assertEqual(res["path"], f"{res['checksum']}.jpg")
        self.assertEqual(res["mime"], "image/jpeg")
        self.assertEqual(res["checksum"], checksum)

    def test_update_media_file(self):
        """Update a media file."""
        img, checksum, size = get_image(1)
        # create
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        # get handle from response
        handle = rv.json[0]["new"]["handle"]
        # check GET ETag
        rv = self.client.get(f"/api/media/{handle}/file", headers=headers)
        self.assertEqual(rv.status_code, 200)
        etag = rv.headers["ETag"]
        self.assertEqual(etag, checksum)
        new_img, new_checksum, new_size = get_image(2)
        self.assertNotEqual(checksum, new_checksum)  # just to be sure
        # try with wrong checksum in If-Match!
        rv = self.client.put(
            f"/api/media/{handle}/file",
            data=new_img.read(),
            headers={**headers, "If-Match": new_checksum},
            content_type="image/jpeg",
        )
        self.assertEqual(rv.status_code, 412)
        new_img.seek(0)
        # try with uploadmissing for existing file!
        rv = self.client.put(
            f"/api/media/{handle}/file?uploadmissing=1",
            data=new_img.read(),
            headers={**headers},
            content_type="image/jpeg",
        )
        self.assertEqual(rv.status_code, 409)
        new_img.seek(0)
        # now it should work
        rv = self.client.put(
            f"/api/media/{handle}/file",
            data=new_img.read(),
            headers={**headers, "If-Match": checksum},
            content_type="image/jpeg",
        )
        self.assertEqual(rv.status_code, 200)
        # get the object
        rv = self.client.get(f"/api/media/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        res = rv.json
        self.assertEqual(res["checksum"], new_checksum)
        self.assertEqual(res["path"], f"{new_checksum}.jpg")

    def test_upload_missing_file(self):
        """Upload a missing media file."""
        img, checksum, size = get_image(3)
        # create
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        # get handle from response
        handle = rv.json[0]["new"]["handle"]
        # check GET ETag
        rv = self.client.get(f"/api/media/{handle}/file", headers=headers)
        self.assertEqual(rv.status_code, 200)
        etag = rv.headers["ETag"]
        self.assertEqual(etag, checksum)
        rv = self.client.get(f"/api/media/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        media_object = rv.json
        # change path!
        media_object["path"] = "newpath.jpg"
        rv = self.client.put(f"/api/media/{handle}", json=media_object, headers=headers)
        # check that handle appears for filemissing
        rv = self.client.get("/api/media/?filemissing=1", headers=headers)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json[0]["handle"], handle)
        # check that fetching file returns 404
        rv = self.client.get(f"/api/media/{handle}/file", headers=headers)
        self.assertEqual(rv.status_code, 404)
        img.seek(0)
        rv = self.client.put(
            f"/api/media/{handle}/file?uploadmissing=1",
            data=img.read(),
            headers=headers,
            content_type="image/jpeg",
        )
        self.assertEqual(rv.status_code, 200)
        rv = self.client.get(f"/api/media/{handle}/file", headers=headers)
        self.assertEqual(rv.status_code, 200)


class TestUploadWithQuota(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.media_base_dir = tempfile.mkdtemp()
        cls.app.config["MEDIA_BASE_DIR"] = cls.media_base_dir
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="admin", password="123", role=ROLE_ADMIN, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        shutil.rmtree(cls.media_base_dir)

    def test_upload_new_media(self):
        """Add new media object."""
        img, checksum, size = get_image(0)
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get("/api/trees/-", headers=headers)
        self.assertEqual(rv.status_code, 200)
        assert rv.json["usage_media"] == size
        tree = rv.json["id"]
        img, checksum, size2 = get_image(1)
        data = {"quota_media": size + size2}
        rv = self.client.put("/api/trees/-", json=data, headers=headers)
        assert rv.status_code == 200
        assert rv.json == data
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get("/api/trees/-", headers=headers)
        self.assertEqual(rv.status_code, 200)
        assert rv.json["usage_media"] == size + size2
        assert rv.json["quota_media"] == size + size2
        img, checksum, size = get_image(2)
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        assert rv.status_code == 405


class TestUploadUsageBackgroundUpdate(unittest.TestCase):
    """Check that the (expensive) usage recompute doesn't block the request."""

    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.media_base_dir = tempfile.mkdtemp()
        cls.app.config["MEDIA_BASE_DIR"] = cls.media_base_dir
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="admin", password="123", role=ROLE_ADMIN, tree=cls.tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        shutil.rmtree(cls.media_base_dir)

    def test_upload_dispatches_usage_update_as_task(self):
        """Adding a media object must hand the usage recompute to the task queue."""
        from gramps_webapi.api.tasks import update_media_usage_task

        headers = get_headers(self.client, "admin", "123")
        img, checksum, size = get_image(0)
        with patch(
            "gramps_webapi.api.resources.media.run_task"
        ) as mock_run_task:
            rv = self.client.post(
                "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
            )
        self.assertEqual(rv.status_code, 201)
        mock_run_task.assert_called_once()
        task = mock_run_task.call_args.args[0]
        self.assertEqual(task.name, update_media_usage_task.name)

    def test_update_file_dispatches_usage_update_as_task(self):
        """Replacing a media file must hand the usage recompute to the task queue."""
        from gramps_webapi.api.tasks import update_media_usage_task

        headers = get_headers(self.client, "admin", "123")
        img, checksum, size = get_image(1)
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        handle = rv.json[0]["new"]["handle"]
        new_img, new_checksum, new_size = get_image(2)
        with patch("gramps_webapi.api.resources.file.run_task") as mock_run_task:
            rv = self.client.put(
                f"/api/media/{handle}/file",
                data=new_img.read(),
                headers={**headers, "If-Match": checksum},
                content_type="image/jpeg",
            )
        self.assertEqual(rv.status_code, 200)
        mock_run_task.assert_called_once()
        task = mock_run_task.call_args.args[0]
        self.assertEqual(task.name, update_media_usage_task.name)

    def test_delete_media_dispatches_usage_update_as_task(self):
        """Deleting a media object must hand the usage recompute to the task queue."""
        from gramps_webapi.api.tasks import update_media_usage_task

        headers = get_headers(self.client, "admin", "123")
        img, checksum, size = get_image(3)
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        handle = rv.json[0]["new"]["handle"]
        with patch("gramps_webapi.api.resources.base.run_task") as mock_run_task:
            rv = self.client.delete(f"/api/media/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        tasks = [call.args[0] for call in mock_run_task.call_args_list]
        self.assertIn(update_media_usage_task.name, [task.name for task in tasks])

    def test_delete_media_by_handle_updates_usage(self):
        """Bulk-deleting media by handle must also bring usage back down.

        This covers DeleteObjectsByHandleResource, which previously only
        resynced usage for the "people" namespace, leaving usage_media stale
        after a bulk media delete.
        """
        headers = get_headers(self.client, "admin", "123")
        img, checksum, size = get_image(12)
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        handle = rv.json[0]["new"]["handle"]
        rv = self.client.get("/api/trees/-", headers=headers)
        self.assertEqual(rv.json["usage_media"], size)
        rv = self.client.post(
            "/api/objects/delete-by-handle/",
            json={"namespace": "media", "handles": [handle]},
            headers=headers,
        )
        self.assertEqual(rv.status_code, 200)
        rv = self.client.get("/api/trees/-", headers=headers)
        self.assertEqual(rv.json["usage_media"], 0)

    def test_upload_duplicate_content_does_not_double_count_usage(self):
        """Uploading the same file content twice must not double-count usage."""
        headers = get_headers(self.client, "admin", "123")
        img, checksum, size = get_image(10)
        img_bytes = img.read()
        rv = self.client.post(
            "/api/media/", data=img_bytes, headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get("/api/trees/-", headers=headers)
        usage_after_first = rv.json["usage_media"]
        # upload the exact same content again as a second, distinct Media object
        rv = self.client.post(
            "/api/media/", data=img_bytes, headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get("/api/trees/-", headers=headers)
        # storage is content-addressed, so the second object reuses the same
        # file on disk - usage must not grow
        self.assertEqual(rv.json["usage_media"], usage_after_first)

    def test_delete_media_updates_usage(self):
        """Deleting the last media object must bring usage back down to zero.

        Without the task queue mocked out, run_task() executes inline (no
        CELERY_CONFIG is set in this test app), so the recompute happens
        synchronously here and can be asserted on directly.
        """
        headers = get_headers(self.client, "admin", "123")
        img, checksum, size = get_image(11)
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        handle = rv.json[0]["new"]["handle"]
        rv = self.client.get("/api/trees/-", headers=headers)
        self.assertEqual(rv.json["usage_media"], size)
        rv = self.client.delete(f"/api/media/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        rv = self.client.get("/api/trees/-", headers=headers)
        self.assertEqual(rv.json["usage_media"], 0)


class TestMediaUsageTaskCoalescing(unittest.TestCase):
    """Check that concurrent dispatches for the same tree coalesce.

    Without this, a burst of N uploads/deletes for the same tree (e.g. the
    sync addon syncing a local tree to an empty instance) dispatches N
    full-tree rescans, the first scanning 1 file, the next 2, etc. - O(N^2).
    """

    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API Coalescing"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.media_base_dir = tempfile.mkdtemp()
        cls.app.config["MEDIA_BASE_DIR"] = cls.media_base_dir
        with cls.app.app_context():
            user_db.create_all()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        shutil.rmtree(cls.media_base_dir)

    def tearDown(self):
        from gramps_webapi.api.cache import persistent_cache

        with self.app.app_context():
            persistent_cache.delete(f"media_usage_recompute_lock:{self.tree}")
            persistent_cache.delete(f"media_usage_recompute_dirty:{self.tree}")

    def test_skips_rescan_while_one_is_already_running(self):
        """A dispatch arriving while a rescan is in-flight must not run a second one."""
        from gramps_webapi.api.cache import persistent_cache
        from gramps_webapi.api.tasks import update_media_usage_task

        with self.app.app_context():
            persistent_cache.add(f"media_usage_recompute_lock:{self.tree}", True)
            with patch(
                "gramps_webapi.api.tasks.update_usage_media"
            ) as mock_update:
                update_media_usage_task(tree=self.tree, user_id="x")
            mock_update.assert_not_called()
            self.assertTrue(
                persistent_cache.get(f"media_usage_recompute_dirty:{self.tree}")
            )

    def test_reruns_once_if_marked_dirty_during_the_rescan(self):
        """A dispatch that arrives mid-rescan triggers exactly one extra rescan."""
        from gramps_webapi.api.cache import persistent_cache
        from gramps_webapi.api.tasks import update_media_usage_task

        dirty_key = f"media_usage_recompute_dirty:{self.tree}"
        call_count = 0

        def fake_update_usage_media(tree, user_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # simulate another dispatch arriving while this rescan runs
                persistent_cache.set(dirty_key, True)

        with self.app.app_context():
            with patch(
                "gramps_webapi.api.tasks.update_usage_media",
                side_effect=fake_update_usage_media,
            ):
                update_media_usage_task(tree=self.tree, user_id="x")
            self.assertEqual(call_count, 2)
            self.assertIsNone(
                persistent_cache.get(f"media_usage_recompute_lock:{self.tree}")
            )
            self.assertIsNone(persistent_cache.get(dirty_key))
