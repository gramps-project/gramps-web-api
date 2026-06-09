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

"""Logging utilities for structured / cloud-friendly log output."""

import json
import logging
import sys

# Cloud Logging uses "severity", not "level", to classify records in Cloud Console.
_LEVEL_TO_SEVERITY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class CloudJsonFormatter(logging.Formatter):
    """JSON formatter with a ``severity`` field for Google Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            message = f"{message}\n{record.exc_text}"
        return json.dumps(
            {
                "severity": _LEVEL_TO_SEVERITY.get(record.levelno, "DEFAULT"),
                "message": message,
                "logger": record.name,
            }
        )


def configure_json_logging(level: int = logging.INFO) -> None:
    """Install a JSON handler on the root logger (used when ``LOG_FORMAT=json``)."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(CloudJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
