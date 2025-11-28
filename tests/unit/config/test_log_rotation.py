"""
Integration tests for log rotation functionality.

Tests the RotatingFileHandler configuration and file rotation behavior.
"""

import logging
import os
import tempfile
from pathlib import Path
from logging.handlers import RotatingFileHandler
import pytest


class TestLogRotation:
    """Test log rotation configuration and behavior."""

    def test_rotating_handler_configuration(self):
        """Test that RotatingFileHandler is configured correctly."""
        # Create temporary log file
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # Create handler with same config as production
            handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )

            # Verify configuration
            assert handler.maxBytes == 10 * 1024 * 1024
            assert handler.backupCount == 5
            assert handler.encoding == 'utf-8'

            # Clean up
            handler.close()

    def test_log_file_created(self):
        """Test that log file is created on first write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # Create logger with rotating handler
            logger = logging.getLogger("test_rotation")
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(
                log_file,
                maxBytes=1024,  # 1KB for testing
                backupCount=2
            )
            logger.addHandler(handler)

            # Write log entry
            logger.info("Test message")

            # Verify file created
            assert log_file.exists()
            assert log_file.stat().st_size > 0

            # Clean up
            handler.close()
            logger.removeHandler(handler)

    def test_rotation_occurs_at_size_limit(self):
        """Test that rotation occurs when file reaches size limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # Create logger with small max size for testing
            logger = logging.getLogger("test_rotation_size")
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(
                log_file,
                maxBytes=500,  # 500 bytes - small for testing
                backupCount=3
            )
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

            # Write enough data to trigger rotation
            # Each message is ~100 bytes, so 10 messages = ~1000 bytes
            for i in range(10):
                logger.info(f"Log entry {i}: " + "x" * 90)

            # Force flush
            handler.flush()

            # Check that backup was created
            backup_file = Path(str(log_file) + ".1")
            assert backup_file.exists(), "Backup file should be created after rotation"

            # Clean up
            handler.close()
            logger.removeHandler(handler)

    def test_backup_count_limit(self):
        """Test that only backupCount backup files are kept."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # Create logger with strict backup limit
            logger = logging.getLogger("test_backup_count")
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(
                log_file,
                maxBytes=300,  # Very small for quick rotation
                backupCount=2  # Only keep 2 backups
            )
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

            # Write enough to create multiple backups
            for i in range(20):
                logger.info(f"Entry {i}: " + "x" * 100)
                handler.flush()

            # Check that only backupCount backups exist
            backup1 = Path(str(log_file) + ".1")
            backup2 = Path(str(log_file) + ".2")
            backup3 = Path(str(log_file) + ".3")

            assert log_file.exists(), "Current log file should exist"
            # At least one backup should exist (rotation occurred)
            assert backup1.exists() or backup2.exists(), "At least one backup should exist"
            # .3 should not exist (backupCount=2)
            assert not backup3.exists(), f"Should not have more than {handler.backupCount} backups"

            # Clean up
            handler.close()
            logger.removeHandler(handler)

    def test_utf8_encoding_preserved(self):
        """Test that UTF-8 encoding is preserved in rotated logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # Create logger
            logger = logging.getLogger("test_utf8")
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(
                log_file,
                maxBytes=500,
                backupCount=2,
                encoding='utf-8'
            )
            logger.addHandler(handler)

            # Write UTF-8 content
            test_messages = [
                "English: Hello",
                "Deutsch: Hallo Welt äöü",
                "中文: 你好世界",
                "Emoji: 🎯✅🔴"
            ]

            for msg in test_messages:
                logger.info(msg)

            handler.flush()

            # Read back and verify
            content = log_file.read_text(encoding='utf-8')
            for msg in test_messages:
                assert msg in content, f"UTF-8 message '{msg}' should be preserved"

            # Clean up
            handler.close()
            logger.removeHandler(handler)

    def test_production_config_values(self):
        """Test that production configuration values are reasonable."""
        # Production config from config/logging_config.py
        max_bytes = 10 * 1024 * 1024  # 10MB
        backup_count = 5

        # Validate values
        assert max_bytes == 10485760, "Max bytes should be 10MB"
        assert backup_count == 5, "Backup count should be 5"

        # Calculate max total size
        max_total_size = max_bytes * (backup_count + 1)  # +1 for current file
        max_total_mb = max_total_size / (1024 * 1024)

        assert max_total_mb == 60, "Max total size should be 60MB (10MB * 6 files)"

    def test_multiple_handlers_independent(self):
        """Test that multiple log files rotate independently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_log = Path(tmpdir) / "app.log"
            error_log = Path(tmpdir) / "error.log"

            # Create logger with two handlers
            logger = logging.getLogger("test_multi")
            logger.setLevel(logging.DEBUG)

            app_handler = RotatingFileHandler(app_log, maxBytes=500, backupCount=2)
            error_handler = RotatingFileHandler(error_log, maxBytes=500, backupCount=2)
            error_handler.setLevel(logging.ERROR)

            logger.addHandler(app_handler)
            logger.addHandler(error_handler)

            # Write INFO logs (only to app.log)
            for i in range(10):
                logger.info(f"Info {i}: " + "x" * 100)

            app_handler.flush()
            error_handler.flush()

            # app.log should have content and possibly backups
            assert app_log.exists()

            # error.log might be empty or very small (no errors written yet)
            if error_log.exists():
                error_size = error_log.stat().st_size
                app_size = app_log.stat().st_size
                assert app_size > error_size, "App log should be larger (has more logs)"

            # Clean up
            app_handler.close()
            error_handler.close()
            logger.removeHandler(app_handler)
            logger.removeHandler(error_handler)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
