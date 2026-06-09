"""Tests for CloudJsonFormatter and configure_json_logging."""

import json
import logging

import pytest

from gramps_webapi.logging_utils import CloudJsonFormatter, configure_json_logging


class TestCloudJsonFormatter:
    def _make_record(self, level, msg, exc_info=None):
        logger = logging.getLogger("test.logger")
        record = logger.makeRecord(
            "test.logger", level, "f", 0, msg, (), exc_info
        )
        return record

    def test_output_is_valid_json(self):
        record = self._make_record(logging.INFO, "hello")
        output = CloudJsonFormatter().format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello"
        assert parsed["logger"] == "test.logger"

    @pytest.mark.parametrize(
        "level,expected",
        [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ],
    )
    def test_severity_mapping(self, level, expected):
        record = self._make_record(level, "msg")
        parsed = json.loads(CloudJsonFormatter().format(record))
        assert parsed["severity"] == expected

    def test_unknown_level_becomes_default(self):
        record = self._make_record(logging.INFO, "msg")
        record.levelno = 99
        parsed = json.loads(CloudJsonFormatter().format(record))
        assert parsed["severity"] == "DEFAULT"

    def test_exception_folded_into_message(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = self._make_record(logging.ERROR, "oops", exc_info=exc_info)
        parsed = json.loads(CloudJsonFormatter().format(record))
        assert "ValueError: boom" in parsed["message"]
        assert "\n" in parsed["message"]


class TestConfigureJsonLogging:
    def setup_method(self):
        """Save and restore root logger state around each test."""
        root = logging.getLogger()
        self._orig_handlers = root.handlers[:]
        self._orig_level = root.level

    def teardown_method(self):
        root = logging.getLogger()
        root.handlers = self._orig_handlers
        root.setLevel(self._orig_level)

    def test_installs_single_handler(self):
        configure_json_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_handler_uses_cloud_json_formatter(self):
        configure_json_logging()
        root = logging.getLogger()
        assert isinstance(root.handlers[0].formatter, CloudJsonFormatter)

    def test_level_is_applied_to_root(self):
        configure_json_logging(level=logging.DEBUG)
        assert logging.getLogger().level == logging.DEBUG

    def test_default_level_is_info(self):
        configure_json_logging()
        assert logging.getLogger().level == logging.INFO

    def test_module_logger_emits_at_configured_level(self, capsys):
        configure_json_logging(level=logging.INFO)
        logger = logging.getLogger("gramps_webapi.some_module")
        logger.propagate = True
        logger.handlers = []
        logger.setLevel(logging.NOTSET)
        logger.info("should appear")
        logger.debug("should not appear")
        captured = capsys.readouterr().err
        lines = [l for l in captured.splitlines() if l.strip()]
        assert len(lines) == 1
        assert json.loads(lines[0])["severity"] == "INFO"
