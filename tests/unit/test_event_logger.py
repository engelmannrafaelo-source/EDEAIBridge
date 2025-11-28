"""
Unit Tests für middleware/event_logger.py - Structured Event Logging

Test Coverage:
- EventLogger - Strukturierte Event-Logging-Klasse
- log_event() - Generic event logging
- log_chat_completion() - Chat completion event logging
- log_authentication() - Authentication event logging
- log_session_event() - Session management event logging
- log_rate_limit_event() - Rate limiting event logging
- log_error_event() - Error event logging
- Convenience function log_event()

WICHTIG: Diese Tests testen NUR die event_logger.py!
"""

import pytest
import json
from unittest.mock import Mock, patch, call
from datetime import datetime
from typing import Dict, Any

# Import zu testende Module
from middleware.event_logger import EventLogger, log_event


# ============================================================================
# Test Class: EventLogger - Generic log_event
# ============================================================================

class TestEventLoggerGeneric:
    """Tests für EventLogger.log_event() generic method."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture: Mock logger für event_logger module."""
        with patch('middleware.event_logger.logger') as mock_log:
            yield mock_log

    def test_logs_basic_event(self, mock_logger):
        """log_event() sollte basic event loggen."""
        EventLogger.log_event(
            event_type="test_event",
            data={"key": "value"}
        )

        # Check logger.info wurde aufgerufen
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]

        # Parse JSON
        assert call_args.startswith("EVENT: ")
        event_json = call_args[7:]  # Remove "EVENT: " prefix
        event = json.loads(event_json)

        assert event["event_type"] == "test_event"
        assert event["data"]["key"] == "value"
        assert "timestamp" in event

    def test_includes_timestamp(self, mock_logger):
        """log_event() sollte ISO 8601 timestamp mit Z suffix inkludieren."""
        EventLogger.log_event(
            event_type="test_event",
            data={}
        )

        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        # Check timestamp format
        timestamp = event["timestamp"]
        assert timestamp.endswith("Z")
        # Verify parseable
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    def test_includes_metadata(self, mock_logger):
        """log_event() sollte metadata inkludieren wenn vorhanden."""
        metadata = {"user_agent": "test-agent", "ip": "127.0.0.1"}

        EventLogger.log_event(
            event_type="test_event",
            data={"action": "test"},
            metadata=metadata
        )

        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["metadata"] == metadata

    def test_respects_log_level(self, mock_logger):
        """log_event() sollte log level respektieren."""
        # INFO level (default)
        EventLogger.log_event(
            event_type="info_event",
            data={},
            level="INFO"
        )
        mock_logger.info.assert_called_once()

        # WARNING level
        EventLogger.log_event(
            event_type="warning_event",
            data={},
            level="WARNING"
        )
        mock_logger.warning.assert_called_once()

        # ERROR level
        EventLogger.log_event(
            event_type="error_event",
            data={},
            level="ERROR"
        )
        mock_logger.error.assert_called_once()


# ============================================================================
# Test Class: EventLogger - log_chat_completion
# ============================================================================

class TestEventLoggerChatCompletion:
    """Tests für EventLogger.log_chat_completion()."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture: Mock logger."""
        with patch('middleware.event_logger.logger') as mock_log:
            yield mock_log

    def test_logs_successful_chat_completion(self, mock_logger):
        """log_chat_completion() sollte successful completion loggen."""
        EventLogger.log_chat_completion(
            session_id="session-123",
            model="claude-sonnet-4",
            message_count=3,
            stream=False,
            duration=2.5,
            tokens=150
        )

        # Check INFO level
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["event_type"] == "chat_completion"
        assert event["data"]["session_id"] == "session-123"
        assert event["data"]["model"] == "claude-sonnet-4"
        assert event["data"]["message_count"] == 3
        assert event["data"]["stream"] is False
        assert event["data"]["duration_seconds"] == 2.5
        assert event["data"]["tokens"] == 150

    def test_logs_streaming_completion(self, mock_logger):
        """log_chat_completion() sollte streaming flag tracken."""
        EventLogger.log_chat_completion(
            session_id="session-123",
            model="claude-sonnet-4",
            message_count=1,
            stream=True
        )

        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["data"]["stream"] is True

    def test_logs_tools_enabled(self, mock_logger):
        """log_chat_completion() sollte tools_enabled tracken."""
        EventLogger.log_chat_completion(
            session_id="session-123",
            model="claude-sonnet-4",
            message_count=1,
            stream=False,
            tools_enabled=True
        )

        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["data"]["tools_enabled"] is True

    def test_logs_chat_completion_error(self, mock_logger):
        """log_chat_completion() sollte errors als ERROR level loggen."""
        EventLogger.log_chat_completion(
            session_id="session-123",
            model="claude-sonnet-4",
            message_count=1,
            stream=False,
            error="Connection timeout"
        )

        # Check ERROR level
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["event_type"] == "chat_completion_error"
        assert event["data"]["error"] == "Connection timeout"

    def test_omits_optional_fields(self, mock_logger):
        """log_chat_completion() sollte None values nicht inkludieren."""
        EventLogger.log_chat_completion(
            session_id="session-123",
            model="claude-sonnet-4",
            message_count=1,
            stream=False
            # duration, tokens, tools_enabled not provided
        )

        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert "duration_seconds" not in event["data"]
        assert "tokens" not in event["data"]
        assert "tools_enabled" not in event["data"]


# ============================================================================
# Test Class: EventLogger - log_authentication
# ============================================================================

class TestEventLoggerAuthentication:
    """Tests für EventLogger.log_authentication()."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture: Mock logger."""
        with patch('middleware.event_logger.logger') as mock_log:
            yield mock_log

    def test_logs_successful_authentication(self, mock_logger):
        """log_authentication() sollte successful auth als INFO loggen."""
        EventLogger.log_authentication(
            success=True,
            method="api_key"
        )

        # Check INFO level
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["event_type"] == "authentication"
        assert event["data"]["success"] is True
        assert event["data"]["method"] == "api_key"

    def test_logs_failed_authentication(self, mock_logger):
        """log_authentication() sollte failed auth als WARNING loggen."""
        EventLogger.log_authentication(
            success=False,
            method="api_key",
            error="Invalid API key"
        )

        # Check WARNING level
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["data"]["success"] is False
        assert event["data"]["error"] == "Invalid API key"

    def test_includes_metadata(self, mock_logger):
        """log_authentication() sollte metadata inkludieren."""
        metadata = {"ip_address": "127.0.0.1", "user_agent": "test"}

        EventLogger.log_authentication(
            success=True,
            method="oauth",
            metadata=metadata
        )

        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["metadata"] == metadata


# ============================================================================
# Test Class: EventLogger - log_session_event
# ============================================================================

class TestEventLoggerSession:
    """Tests für EventLogger.log_session_event()."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture: Mock logger."""
        with patch('middleware.event_logger.logger') as mock_log:
            yield mock_log

    def test_logs_session_created(self, mock_logger):
        """log_session_event() sollte session creation loggen."""
        EventLogger.log_session_event(
            event_subtype="created",
            session_id="session-123"
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["event_type"] == "session_management"
        assert event["data"]["subtype"] == "created"
        assert event["data"]["session_id"] == "session-123"

    def test_includes_session_details(self, mock_logger):
        """log_session_event() sollte details inkludieren."""
        details = {"user_id": "user-456", "mode": "session"}

        EventLogger.log_session_event(
            event_subtype="updated",
            session_id="session-123",
            details=details
        )

        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["data"]["user_id"] == "user-456"
        assert event["data"]["mode"] == "session"


# ============================================================================
# Test Class: EventLogger - log_rate_limit_event
# ============================================================================

class TestEventLoggerRateLimit:
    """Tests für EventLogger.log_rate_limit_event()."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture: Mock logger."""
        with patch('middleware.event_logger.logger') as mock_log:
            yield mock_log

    def test_logs_rate_limit_info(self, mock_logger):
        """log_rate_limit_event() sollte rate limit als INFO loggen."""
        EventLogger.log_rate_limit_event(
            endpoint="/v1/chat/completions",
            limit=100,
            window="1m",
            exceeded=False
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["event_type"] == "rate_limit"
        assert event["data"]["endpoint"] == "/v1/chat/completions"
        assert event["data"]["limit"] == 100
        assert event["data"]["window"] == "1m"
        assert event["data"]["exceeded"] is False

    def test_logs_rate_limit_exceeded(self, mock_logger):
        """log_rate_limit_event() sollte exceeded als WARNING loggen."""
        EventLogger.log_rate_limit_event(
            endpoint="/v1/chat/completions",
            limit=100,
            window="1m",
            exceeded=True
        )

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["data"]["exceeded"] is True


# ============================================================================
# Test Class: EventLogger - log_error_event
# ============================================================================

class TestEventLoggerError:
    """Tests für EventLogger.log_error_event()."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture: Mock logger."""
        with patch('middleware.event_logger.logger') as mock_log:
            yield mock_log

    def test_logs_error_event(self, mock_logger):
        """log_error_event() sollte error als ERROR level loggen."""
        EventLogger.log_error_event(
            error_type="ValidationError",
            error_message="Invalid request format",
            endpoint="/v1/chat/completions"
        )

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["event_type"] == "error"
        assert event["data"]["error_type"] == "ValidationError"
        assert event["data"]["error_message"] == "Invalid request format"
        assert event["data"]["endpoint"] == "/v1/chat/completions"

    def test_error_without_endpoint(self, mock_logger):
        """log_error_event() sollte ohne endpoint funktionieren."""
        EventLogger.log_error_event(
            error_type="SystemError",
            error_message="Internal error"
        )

        call_args = mock_logger.error.call_args[0][0]
        event = json.loads(call_args[7:])

        assert "endpoint" not in event["data"]

    def test_error_with_metadata(self, mock_logger):
        """log_error_event() sollte metadata inkludieren."""
        metadata = {"stack_trace": "...", "user_id": "user-123"}

        EventLogger.log_error_event(
            error_type="RuntimeError",
            error_message="Unexpected error",
            metadata=metadata
        )

        call_args = mock_logger.error.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["metadata"] == metadata


# ============================================================================
# Test Class: Convenience Function
# ============================================================================

class TestConvenienceFunction:
    """Tests für convenience function log_event()."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture: Mock logger."""
        with patch('middleware.event_logger.logger') as mock_log:
            yield mock_log

    def test_convenience_function_works(self, mock_logger):
        """log_event() convenience function sollte funktionieren."""
        log_event(
            event_type="custom_event",
            data={"custom": "data"},
            metadata={"meta": "info"},
            level="WARNING"
        )

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        event = json.loads(call_args[7:])

        assert event["event_type"] == "custom_event"
        assert event["data"]["custom"] == "data"
        assert event["metadata"]["meta"] == "info"


# ============================================================================
# Test Summary
# ============================================================================

"""
Test Summary für middleware/event_logger.py:

✅ Test Coverage:
- EventLogger Generic (4 Tests) - log_event(), timestamp, metadata, log levels
- Chat Completion (5 Tests) - success, streaming, tools, errors, optional fields
- Authentication (3 Tests) - success, failure, metadata
- Session Events (2 Tests) - creation, details
- Rate Limiting (2 Tests) - info, exceeded warning
- Error Events (3 Tests) - basic, without endpoint, with metadata
- Convenience Function (1 Test) - log_event() wrapper

Total: 20 Tests

🎯 Test Strategy:
- EventLogger: Unit tests für alle static methods
- JSON Parsing: Verify event structure und required fields
- Log Levels: Verify INFO/WARNING/ERROR based on event type
- Optional Fields: Test None handling (fields not included)
- Metadata: Test metadata propagation

📝 Key Patterns:
- Mock logger für event_logger module
- JSON parsing für event verification
- Timestamp format validation (ISO 8601 + Z)
- Log level verification (info/warning/error)
- Optional field handling (None → not included)
"""
