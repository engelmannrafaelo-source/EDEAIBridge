"""
Unit Tests für claude_cli.py - Claude Code CLI Session Management

Test Coverage:
- ClaudeCodeCLI.__init__() - Konstruktor mit Auth-Validation
- verify_cli() - CLI SDK Verification
- run_completion() - Completion mit verschiedenen Optionen
- parse_claude_message() - Message Parsing (alte + neue SDK Formate)
- extract_metadata() - Metadata Extraction
- Error Handling - Timeouts, Cancellation, SDK Errors
- Session Tracking - Integration mit cli_session_manager

WICHTIG: Diese Tests testen NUR die claude_cli.py Funktionalität!
         Auth-Validation wird gemockt (bereits in test_auth.py getestet).
"""

import pytest
import asyncio
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime
from typing import AsyncIterator, Dict, Any

# Import zu testende Module
from src.claude_cli import ClaudeCodeCLI
from src.models import ChatCompletionRequest, Message


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_auth_manager():
    """Mock: auth_manager mit get_claude_code_env_vars()."""
    with patch('auth.auth_manager') as mock_manager:
        mock_manager.get_claude_code_env_vars.return_value = {}
        yield mock_manager


@pytest.fixture
def mock_auth_valid(mock_auth_manager):
    """Mock: validate_claude_code_auth() gibt True zurück."""
    with patch('auth.validate_claude_code_auth') as mock_validate:
        mock_validate.return_value = (True, {"valid": True, "method": "claude_cli"})
        yield mock_validate


@pytest.fixture
def mock_auth_invalid(mock_auth_manager):
    """Mock: validate_claude_code_auth() gibt False zurück."""
    with patch('auth.validate_claude_code_auth') as mock_validate:
        mock_validate.return_value = (False, {
            "valid": False,
            "method": "claude_cli",
            "errors": ["No active Claude CLI session"]
        })
        yield mock_validate


@pytest.fixture
def mock_session_manager():
    """Mock: cli_session_manager für Session-Tracking."""
    with patch('cli_session_manager.cli_session_manager') as mock_manager:
        # create_session() returns CLISession object with cli_session_id and cancellation_token
        mock_session = Mock()
        mock_session.cli_session_id = "test-session-123"
        mock_session.cancellation_token.is_set.return_value = False  # Not cancelled
        mock_manager.create_session.return_value = mock_session
        mock_manager.complete_session = Mock()
        yield mock_manager


@pytest.fixture
def sample_request():
    """Sample ChatCompletionRequest für Tests."""
    return ChatCompletionRequest(
        model="claude-sonnet-4",
        messages=[
            Message(role="user", content="Hello, Claude!")
        ],
        stream=False,
        enable_tools=False
    )


# ============================================================================
# Test Class: ClaudeCodeCLI.__init__()
# ============================================================================

class TestClaudeCodeCLIInit:
    """Tests für ClaudeCodeCLI Konstruktor."""

    def test_init_default_values(self, mock_auth_valid):
        """Konstruktor sollte default Werte korrekt setzen."""
        cli = ClaudeCodeCLI()

        assert cli.timeout == 600  # Default timeout: 600000ms / 1000 = 600 seconds
        assert cli.cwd == Path.cwd()  # Current working directory as Path object
        # Auth validation sollte aufgerufen worden sein
        mock_auth_valid.assert_called_once()

    def test_init_custom_timeout(self, mock_auth_valid):
        """Konstruktor sollte custom timeout akzeptieren."""
        cli = ClaudeCodeCLI(timeout=120000)  # 120000ms = 120 seconds

        assert cli.timeout == 120  # 120000 / 1000 = 120

    def test_init_custom_cwd(self, mock_auth_valid):
        """Konstruktor sollte custom cwd akzeptieren."""
        custom_cwd = "/tmp/test"
        cli = ClaudeCodeCLI(cwd=custom_cwd)

        assert cli.cwd == Path(custom_cwd)  # Path object comparison

    def test_init_with_invalid_auth_logs_warning(self, mock_auth_invalid, caplog):
        """Mit invalid auth sollte Warning geloggt werden."""
        cli = ClaudeCodeCLI()

        # Check dass Warning geloggt wurde
        assert "Claude Code authentication issues detected" in caplog.text
        assert "No active Claude CLI session" in caplog.text


# ============================================================================
# Test Class: verify_cli()
# ============================================================================

class TestVerifyCLI:
    """Tests für verify_cli() Methode."""

    @pytest.mark.asyncio
    async def test_verify_cli_success(self, mock_auth_valid):
        """verify_cli() sollte bei erfolgreicher Verbindung True zurückgeben."""
        cli = ClaudeCodeCLI()

        # Mock query() - muss async generator sein
        async def mock_query_generator(*args, **kwargs):
            yield {"type": "result", "subtype": "success"}

        with patch('claude_cli.query', side_effect=mock_query_generator):
            result = await cli.verify_cli()

            assert result is True

    @pytest.mark.asyncio
    async def test_verify_cli_timeout(self, mock_auth_valid):
        """verify_cli() sollte bei Timeout False zurückgeben."""
        cli = ClaudeCodeCLI(timeout=1)

        # Mock: Simuliere Timeout
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(2)
            return []

        with patch('claude_cli.query', side_effect=slow_query):
            result = await cli.verify_cli()

            assert result is False

    @pytest.mark.asyncio
    async def test_verify_cli_sdk_error(self, mock_auth_valid, caplog):
        """verify_cli() sollte bei SDK Error False zurückgeben."""
        cli = ClaudeCodeCLI()

        # Mock: Simuliere SDK Exception
        with patch('claude_cli.query', side_effect=Exception("SDK Error")):
            result = await cli.verify_cli()

            assert result is False
            assert "Claude Code SDK verification failed" in caplog.text


# ============================================================================
# Test Class: run_completion()
# ============================================================================

class TestRunCompletion:
    """Tests für run_completion() Methode."""

    @pytest.mark.asyncio
    async def test_run_completion_success(self, mock_auth_valid, mock_session_manager, sample_request):
        """run_completion() sollte erfolgreich Messages yielden."""
        cli = ClaudeCodeCLI()

        # Mock claude_code_sdk.query() - Simulate streaming response
        mock_messages = [
            {"type": "system", "subtype": "init", "session_id": "test-123", "model": "claude-sonnet-4"},
            {"type": "assistant", "content": "Hello! How can I help?"},
            {"type": "result", "subtype": "success", "total_cost_usd": 0.05, "duration_ms": 1500, "num_turns": 1}
        ]

        async def mock_query_generator(*args, **kwargs):
            for msg in mock_messages:
                yield msg

        with patch('claude_cli.query', side_effect=mock_query_generator):
            messages = []
            async for message in cli.run_completion(sample_request):
                messages.append(message)

            # Verify: Messages wurden yielded
            assert len(messages) == 3
            assert messages[0]["type"] == "system"
            assert messages[1]["type"] == "assistant"
            assert messages[2]["type"] == "result"

            # Verify: Session wurde created und completed
            mock_session_manager.create_session.assert_called_once()
            mock_session_manager.complete_session.assert_called_once_with("test-session-123", status="completed")

    @pytest.mark.asyncio
    async def test_run_completion_with_tools_enabled(self, mock_auth_valid, mock_session_manager):
        """run_completion() sollte Tools aktivieren wenn enable_tools=True."""
        cli = ClaudeCodeCLI()

        request = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="List files")],
            enable_tools=True
        )

        mock_messages = [
            {"type": "result", "subtype": "success"}
        ]

        async def mock_query_generator(*args, **kwargs):
            # Verify: tools parameter wurde übergeben
            assert 'tools' in kwargs
            assert kwargs['tools'] is None  # None = all tools enabled
            for msg in mock_messages:
                yield msg

        with patch('claude_cli.query', side_effect=mock_query_generator):
            async for _ in cli.run_completion(request):
                pass

    @pytest.mark.asyncio
    async def test_run_completion_with_tools_disabled(self, mock_auth_valid, mock_session_manager):
        """run_completion() sollte Tools deaktivieren wenn enable_tools=False."""
        cli = ClaudeCodeCLI()

        request = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            enable_tools=False
        )

        mock_messages = [
            {"type": "result", "subtype": "success"}
        ]

        async def mock_query_generator(*args, **kwargs):
            # Verify: tools parameter wurde auf [] gesetzt (no tools)
            assert 'tools' in kwargs
            assert kwargs['tools'] == []
            for msg in mock_messages:
                yield msg

        with patch('claude_cli.query', side_effect=mock_query_generator):
            async for _ in cli.run_completion(request):
                pass

    @pytest.mark.asyncio
    async def test_run_completion_timeout(self, mock_auth_valid, mock_session_manager, sample_request):
        """run_completion() sollte bei Timeout Session als failed markieren."""
        cli = ClaudeCodeCLI(timeout=1)

        # Mock: Simuliere langsame Query die timeout triggert
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(2)
            yield {"type": "result"}

        with patch('claude_cli.query', side_effect=slow_query):
            with pytest.raises(asyncio.TimeoutError):
                async for _ in cli.run_completion(sample_request):
                    pass

            # Verify: Session wurde als failed markiert
            mock_session_manager.complete_session.assert_called_once_with("test-session-123", status="failed")

    @pytest.mark.asyncio
    async def test_run_completion_cancelled(self, mock_auth_valid, mock_session_manager, sample_request):
        """run_completion() sollte bei CancelledError Session als cancelled markieren."""
        cli = ClaudeCodeCLI()

        # Mock: Simuliere cancellation via cancellation_token
        mock_session_manager.create_session.return_value.cancellation_token.is_set.return_value = True

        async def mock_query_generator(*args, **kwargs):
            yield {"type": "result", "subtype": "success"}

        with patch('claude_cli.query', side_effect=mock_query_generator):
            with pytest.raises(asyncio.CancelledError):
                async for _ in cli.run_completion(sample_request):
                    pass

            # Verify: Session wurde als cancelled markiert
            mock_session_manager.complete_session.assert_called_once_with("test-session-123", status="cancelled")

    @pytest.mark.asyncio
    async def test_run_completion_sdk_error(self, mock_auth_valid, mock_session_manager, sample_request):
        """run_completion() sollte bei SDK Error error message yielden."""
        cli = ClaudeCodeCLI()

        # Mock: Simuliere SDK Exception DURING iteration
        async def error_query(*args, **kwargs):
            if False:  # Make this an async generator
                yield
            raise Exception("SDK Connection Error")

        with patch('claude_cli.query', side_effect=error_query):
            messages = []
            async for message in cli.run_completion(sample_request):
                messages.append(message)

            # Verify: Error message wurde yielded
            assert len(messages) == 1
            assert messages[0]["type"] == "result"
            assert messages[0]["subtype"] == "error_during_execution"
            assert messages[0]["is_error"] is True
            assert "SDK Connection Error" in messages[0]["error_message"]

            # Verify: Session wurde als failed markiert
            mock_session_manager.complete_session.assert_called_once_with("test-session-123", status="failed")


# ============================================================================
# Test Class: parse_claude_message()
# ============================================================================

class TestParseClaudeMessage:
    """Tests für parse_claude_message() Methode."""

    def test_parse_new_sdk_format_with_text_blocks(self, mock_auth_valid):
        """parse_claude_message() sollte neues SDK Format mit TextBlocks parsen."""
        cli = ClaudeCodeCLI()

        # Mock: Neue SDK Format Messages mit TextBlock objects
        messages = [
            {
                "content": [
                    type("TextBlock", (), {"text": "Hello, "})(),
                    type("TextBlock", (), {"text": "World!"})()
                ]
            }
        ]

        result = cli.parse_claude_message(messages)

        assert result == "Hello, \nWorld!"

    def test_parse_new_sdk_format_with_dict_blocks(self, mock_auth_valid):
        """parse_claude_message() sollte neues SDK Format mit dict blocks parsen."""
        cli = ClaudeCodeCLI()

        messages = [
            {
                "content": [
                    {"type": "text", "text": "First line"},
                    {"type": "text", "text": "Second line"}
                ]
            }
        ]

        result = cli.parse_claude_message(messages)

        assert result == "First line\nSecond line"

    def test_parse_old_sdk_format(self, mock_auth_valid):
        """parse_claude_message() sollte altes SDK Format parsen."""
        cli = ClaudeCodeCLI()

        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Old format message"}
                    ]
                }
            }
        ]

        result = cli.parse_claude_message(messages)

        assert result == "Old format message"

    def test_parse_old_format_with_string_content(self, mock_auth_valid):
        """parse_claude_message() sollte string content direkt zurückgeben."""
        cli = ClaudeCodeCLI()

        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": "Direct string message"
                }
            }
        ]

        result = cli.parse_claude_message(messages)

        assert result == "Direct string message"

    def test_parse_no_assistant_message(self, mock_auth_valid):
        """parse_claude_message() sollte None zurückgeben wenn keine assistant message."""
        cli = ClaudeCodeCLI()

        messages = [
            {"type": "system", "subtype": "init"},
            {"type": "result", "subtype": "success"}
        ]

        result = cli.parse_claude_message(messages)

        assert result is None

    def test_parse_empty_messages(self, mock_auth_valid):
        """parse_claude_message() sollte None zurückgeben bei leerer Liste."""
        cli = ClaudeCodeCLI()

        result = cli.parse_claude_message([])

        assert result is None


# ============================================================================
# Test Class: extract_metadata()
# ============================================================================

class TestExtractMetadata:
    """Tests für extract_metadata() Methode."""

    def test_extract_metadata_new_format(self, mock_auth_valid):
        """extract_metadata() sollte metadata aus neuem SDK Format extrahieren."""
        cli = ClaudeCodeCLI()

        messages = [
            {
                "subtype": "init",
                "data": {
                    "session_id": "session-123",
                    "model": "claude-sonnet-4"
                }
            },
            {
                "subtype": "success",
                "total_cost_usd": 0.05,
                "duration_ms": 1500,
                "num_turns": 2,
                "session_id": "session-123"
            }
        ]

        metadata = cli.extract_metadata(messages)

        assert metadata["session_id"] == "session-123"
        assert metadata["model"] == "claude-sonnet-4"
        assert metadata["total_cost_usd"] == 0.05
        assert metadata["duration_ms"] == 1500
        assert metadata["num_turns"] == 2

    def test_extract_metadata_old_format(self, mock_auth_valid):
        """extract_metadata() sollte metadata aus altem SDK Format extrahieren."""
        cli = ClaudeCodeCLI()

        messages = [
            {
                "type": "system",
                "subtype": "init",
                "session_id": "old-session-456",
                "model": "claude-opus-3"
            },
            {
                "type": "result",
                "total_cost_usd": 0.10,
                "duration_ms": 2000,
                "num_turns": 3,
                "session_id": "old-session-456"
            }
        ]

        metadata = cli.extract_metadata(messages)

        assert metadata["session_id"] == "old-session-456"
        assert metadata["model"] == "claude-opus-3"
        assert metadata["total_cost_usd"] == 0.10
        assert metadata["duration_ms"] == 2000
        assert metadata["num_turns"] == 3

    def test_extract_metadata_defaults(self, mock_auth_valid):
        """extract_metadata() sollte defaults zurückgeben wenn keine metadata."""
        cli = ClaudeCodeCLI()

        messages = [
            {"type": "assistant", "content": "Some response"}
        ]

        metadata = cli.extract_metadata(messages)

        assert metadata["session_id"] is None
        assert metadata["total_cost_usd"] == 0.0
        assert metadata["duration_ms"] == 0
        assert metadata["num_turns"] == 0
        assert metadata["model"] is None

    def test_extract_metadata_empty_messages(self, mock_auth_valid):
        """extract_metadata() sollte defaults bei leerer Liste zurückgeben."""
        cli = ClaudeCodeCLI()

        metadata = cli.extract_metadata([])

        assert metadata["session_id"] is None
        assert metadata["total_cost_usd"] == 0.0
        assert metadata["duration_ms"] == 0
        assert metadata["num_turns"] == 0
        assert metadata["model"] is None


# ============================================================================
# Test Summary
# ============================================================================

"""
Test Summary für claude_cli.py:

✅ Test Coverage:
- __init__() - 4 Tests (default values, custom params, auth validation)
- verify_cli() - 3 Tests (success, timeout, error)
- run_completion() - 6 Tests (success, tools, timeout, cancelled, error, session tracking)
- parse_claude_message() - 6 Tests (new/old formats, string content, edge cases)
- extract_metadata() - 4 Tests (new/old formats, defaults, empty)

Total: 23 Tests

🎯 Test Strategy:
- Auth validation wird gemockt (bereits in test_auth.py getestet)
- Session manager wird gemockt (wird in test_session_manager.py getestet)
- claude_code_sdk.query() wird gemockt (externe Dependency)
- Fokus auf ClaudeCodeCLI Logik und Error Handling

⚠️ Known Limitations:
- claude_code_sdk.query() ist externe Dependency (nicht testbar ohne Mock)
- Async generator testing erfordert spezielle Mock-Strategie
- TextBlock objects werden mit type() dynamisch erstellt (SDK nicht verfügbar)
"""
