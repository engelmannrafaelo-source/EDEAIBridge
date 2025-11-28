"""
Tests for centralized logging configuration.

Tests logging setup, backwards compatibility, and security filtering.
"""

import os
import logging
import tempfile
import shutil
from pathlib import Path
import pytest

from config.logging_config import setup_logging, get_logger, SensitiveDataFilter


class TestLoggingSetup:
    """Test basic logging setup and configuration."""

    def setup_method(self):
        """Reset logging before each test."""
        # Remove all handlers from root logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

        # Reset root logger level
        root_logger.setLevel(logging.WARNING)

    def test_setup_logging_console_only(self):
        """Test setup with console logging only."""
        setup_logging(log_level='INFO', log_to_file=False)
        logger = get_logger(__name__)

        # Logger inherits from root logger, so check root logger level
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert logger.isEnabledFor(logging.INFO)

    def test_setup_logging_with_debug_level(self):
        """Test DEBUG log level setup."""
        setup_logging(log_level='DEBUG', log_to_file=False)
        logger = get_logger(__name__)

        # Logger inherits from root logger, so check root logger level
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert logger.isEnabledFor(logging.DEBUG)

    def test_get_logger_returns_logger(self):
        """Test get_logger returns proper logger instance."""
        logger = get_logger('test.module')

        assert isinstance(logger, logging.Logger)
        assert logger.name == 'test.module'


class TestBackwardsCompatibility:
    """Test backwards compatibility with DEBUG_MODE and VERBOSE."""

    def test_debug_mode_overrides_log_level(self):
        """Test DEBUG_MODE=true overrides LOG_LEVEL."""
        os.environ['DEBUG_MODE'] = 'true'
        os.environ['LOG_LEVEL'] = 'INFO'

        # Simulate main.py logic
        if os.getenv('DEBUG_MODE', 'false').lower() in ('true', '1', 'yes', 'on'):
            log_level = 'DEBUG'
        else:
            log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

        assert log_level == 'DEBUG'

        # Cleanup
        del os.environ['DEBUG_MODE']
        del os.environ['LOG_LEVEL']

    def test_verbose_overrides_log_level(self):
        """Test VERBOSE=true overrides LOG_LEVEL."""
        os.environ['DEBUG_MODE'] = 'false'
        os.environ['VERBOSE'] = 'true'
        os.environ['LOG_LEVEL'] = 'INFO'

        # Simulate main.py logic
        if os.getenv('DEBUG_MODE', 'false').lower() in ('true', '1', 'yes', 'on') or \
           os.getenv('VERBOSE', 'false').lower() in ('true', '1', 'yes', 'on'):
            log_level = 'DEBUG'
        else:
            log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

        assert log_level == 'DEBUG'

        # Cleanup
        del os.environ['DEBUG_MODE']
        del os.environ['VERBOSE']
        del os.environ['LOG_LEVEL']

    def test_log_level_used_when_no_debug_or_verbose(self):
        """Test LOG_LEVEL is used when DEBUG_MODE/VERBOSE are false."""
        os.environ['DEBUG_MODE'] = 'false'
        os.environ['VERBOSE'] = 'false'
        os.environ['LOG_LEVEL'] = 'WARNING'

        # Simulate main.py logic
        if os.getenv('DEBUG_MODE', 'false').lower() in ('true', '1', 'yes', 'on') or \
           os.getenv('VERBOSE', 'false').lower() in ('true', '1', 'yes', 'on'):
            log_level = 'DEBUG'
        else:
            log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

        assert log_level == 'WARNING'

        # Cleanup
        del os.environ['DEBUG_MODE']
        del os.environ['VERBOSE']
        del os.environ['LOG_LEVEL']


class TestSensitiveDataFilter:
    """Test sensitive data filtering (API keys, passwords)."""

    def setup_method(self):
        """Setup test filter."""
        self.filter = SensitiveDataFilter()

    def test_filters_api_key_in_message(self):
        """Test API key is masked in log message."""
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='API_KEY=sk-1234567890abcdefghij',
            args=(),
            exc_info=None
        )

        result = self.filter.filter(record)

        assert result is True  # Record is not blocked
        assert 'sk-1234567890abcdefghij' not in record.getMessage()
        assert '***' in record.getMessage()

    def test_filters_bearer_token(self):
        """Test Bearer token is masked."""
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Authorization: Bearer sk-ant-1234567890abcdefghij',
            args=(),
            exc_info=None
        )

        result = self.filter.filter(record)

        assert result is True
        assert 'sk-ant-1234567890abcdefghij' not in record.getMessage()
        assert '***' in record.getMessage()

    def test_filters_password_in_json(self):
        """Test password is masked in JSON-like strings."""
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='{"username": "user", "password": "SuperSecret123"}',
            args=(),
            exc_info=None
        )

        result = self.filter.filter(record)

        assert result is True
        assert 'SuperSecret123' not in record.getMessage()
        assert '***' in record.getMessage()

    def test_does_not_filter_normal_message(self):
        """Test normal messages pass through unchanged."""
        original_msg = 'This is a normal log message without secrets'
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg=original_msg,
            args=(),
            exc_info=None
        )

        result = self.filter.filter(record)

        assert result is True
        assert record.getMessage() == original_msg


class TestFileLogging:
    """Test file-based logging with rotation."""

    def setup_method(self):
        """Create temporary logs directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.logs_dir = Path(self.temp_dir) / 'logs'
        self.logs_dir.mkdir()

        # Override logs directory
        import config.logging_config as lc
        self.original_logs_dir = lc.LOGS_DIR
        lc.LOGS_DIR = self.logs_dir

    def teardown_method(self):
        """Cleanup temporary directory."""
        import config.logging_config as lc
        lc.LOGS_DIR = self.original_logs_dir

        # Remove all handlers to release file locks
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

        shutil.rmtree(self.temp_dir)

    def test_creates_log_files(self):
        """Test that log files are created."""
        setup_logging(log_level='INFO', log_to_file=True)
        logger = get_logger(__name__)

        logger.info("Test message")
        logger.error("Test error")

        # Flush handlers
        for handler in logging.getLogger().handlers:
            handler.flush()

        # Check files exist
        app_log = self.logs_dir / 'app.log'
        error_log = self.logs_dir / 'error.log'

        assert app_log.exists(), f"app.log not found in {self.logs_dir}"
        assert error_log.exists(), f"error.log not found in {self.logs_dir}"

        # Check content
        app_content = app_log.read_text()
        error_content = error_log.read_text()

        assert 'Test message' in app_content
        assert 'Test error' in app_content
        assert 'Test error' in error_content


class TestDiagnosticLogging:
    """Test diagnostic logging with emoji markers."""

    def test_diagnostic_filter_detects_emoji_markers(self):
        """Test diagnostic filter recognizes emoji markers."""
        from config.logging_config import DiagnosticFilter

        filter = DiagnosticFilter()

        # Test with diagnostic marker
        record_with_marker = logging.LogRecord(
            name='test',
            level=logging.ERROR,
            pathname='test.py',
            lineno=1,
            msg='🔴 Critical bug detected',
            args=(),
            exc_info=None
        )

        assert filter.filter(record_with_marker) is True

        # Test without diagnostic marker
        record_without_marker = logging.LogRecord(
            name='test',
            level=logging.ERROR,
            pathname='test.py',
            lineno=1,
            msg='Normal error message',
            args=(),
            exc_info=None
        )

        assert filter.filter(record_without_marker) is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
