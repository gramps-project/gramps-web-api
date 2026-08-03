#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2026      David Straub
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

"""WSGI entry point for gunicorn."""

import logging

from .app import create_app

app = create_app()

# when using gunicorn, make sure flask log messages are shown
gunicorn_logger = logging.getLogger("gunicorn.error")
if app.config.get("LOG_FORMAT") == "json":
    # Gunicorn's own loggers have propagate=False and their own plain-text
    # handler; point them at the root logger's JSON handler instead.
    json_handler = logging.getLogger().handlers[0]
    gunicorn_logger.handlers = [json_handler]
    logging.getLogger("gunicorn.access").handlers = [json_handler]
    app.logger.setLevel(gunicorn_logger.level or logging.INFO)
else:
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
