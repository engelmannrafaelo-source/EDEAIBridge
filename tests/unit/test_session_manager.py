"""
Unit Tests für session_manager.py - HTTP Session Management

Test Coverage:
- Session dataclass - touch(), add_messages(), get_all_messages(), is_expired(), to_session_info()
- SessionManager.__init__() - Initialization with default/custom TTL
- get_or_create_session() - Create new, reuse existing, recreate expired
- get_session() - Get without create, expire handling
- delete_session() - Session deletion
- list_sessions() - List active sessions, auto-cleanup expired
- process_messages() - Stateless vs session mode, message accumulation
- add_assistant_response() - Add responses to sessions
- get_stats() - Session statistics
- start_cleanup_task() - Async cleanup task
- shutdown() - Cleanup and shutdown

WICHTIG: Diese Tests testen NUR die session_manager.py Funktionalität!
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from typing import List

# Import zu testende Module
from src.session_manager import Session, SessionManager
from src.models import Message, SessionInfo


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_messages():
    """Sample messages für Tests."""
    return [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there!"),
        Message(role="user", content="How are you?")
    ]


@pytest.fixture
def manager():
    """Fresh SessionManager instance für jeden Test."""
    return SessionManager(default_ttl_hours=1, cleanup_interval_minutes=5)


# ============================================================================
# Test Class: Session Dataclass
# ============================================================================

class TestSession:
    """Tests für Session dataclass."""

    def test_session_creation_defaults(self):
        """Session sollte mit defaults erstellt werden."""
        session = Session(session_id="test-123")

        assert session.session_id == "test-123"
        assert session.messages == []
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_accessed, datetime)
        assert isinstance(session.expires_at, datetime)

    def test_session_expiration_time(self):
        """Session sollte default 1h TTL haben."""
        session = Session(session_id="test-123")

        # expires_at sollte ~1h in Zukunft sein
        expected_expiry = datetime.utcnow() + timedelta(hours=1)
        time_diff = abs((session.expires_at - expected_expiry).total_seconds())

        assert time_diff < 5  # Max 5s Differenz (wegen Ausführungszeit)

    def test_touch_updates_last_accessed(self):
        """touch() sollte last_accessed aktualisieren."""
        session = Session(session_id="test-123")
        original_last_accessed = session.last_accessed

        # Wait a bit
        import time
        time.sleep(0.01)

        session.touch()

        assert session.last_accessed > original_last_accessed

    def test_touch_extends_expiration(self):
        """touch() sollte expiration verlängern."""
        session = Session(session_id="test-123")
        original_expires = session.expires_at

        # Wait a bit
        import time
        time.sleep(0.01)

        session.touch()

        assert session.expires_at > original_expires

    def test_add_messages(self, sample_messages):
        """add_messages() sollte Messages hinzufügen."""
        session = Session(session_id="test-123")

        session.add_messages(sample_messages[:2])

        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[1].role == "assistant"

    def test_add_messages_touches_session(self):
        """add_messages() sollte session touchen."""
        session = Session(session_id="test-123")
        original_last_accessed = session.last_accessed

        import time
        time.sleep(0.01)

        session.add_messages([Message(role="user", content="test")])

        assert session.last_accessed > original_last_accessed

    def test_get_all_messages(self, sample_messages):
        """get_all_messages() sollte alle Messages zurückgeben."""
        session = Session(session_id="test-123")
        session.add_messages(sample_messages)

        all_messages = session.get_all_messages()

        assert len(all_messages) == 3
        assert all_messages == sample_messages

    def test_is_expired_false_for_new_session(self):
        """is_expired() sollte False für neue Session sein."""
        session = Session(session_id="test-123")

        assert session.is_expired() is False

    def test_is_expired_true_for_old_session(self):
        """is_expired() sollte True für abgelaufene Session sein."""
        session = Session(session_id="test-123")
        # Set expiration to past
        session.expires_at = datetime.utcnow() - timedelta(hours=1)

        assert session.is_expired() is True

    def test_to_session_info(self, sample_messages):
        """to_session_info() sollte SessionInfo erstellen."""
        session = Session(session_id="test-123")
        session.add_messages(sample_messages)

        info = session.to_session_info()

        assert isinstance(info, SessionInfo)
        assert info.session_id == "test-123"
        assert info.message_count == 3
        assert info.created_at == session.created_at
        assert info.expires_at == session.expires_at


# ============================================================================
# Test Class: SessionManager.__init__()
# ============================================================================

class TestSessionManagerInit:
    """Tests für SessionManager Konstruktor."""

    def test_init_default_values(self):
        """SessionManager sollte mit defaults initialisiert werden."""
        manager = SessionManager()

        assert manager.default_ttl_hours == 1
        assert manager.cleanup_interval_minutes == 5
        assert manager.sessions == {}
        assert manager._cleanup_task is None

    def test_init_custom_ttl(self):
        """SessionManager sollte custom TTL akzeptieren."""
        manager = SessionManager(default_ttl_hours=2, cleanup_interval_minutes=10)

        assert manager.default_ttl_hours == 2
        assert manager.cleanup_interval_minutes == 10


# ============================================================================
# Test Class: get_or_create_session()
# ============================================================================

class TestGetOrCreateSession:
    """Tests für get_or_create_session()."""

    def test_creates_new_session(self, manager):
        """get_or_create_session() sollte neue Session erstellen."""
        session = manager.get_or_create_session("new-session")

        assert session.session_id == "new-session"
        assert "new-session" in manager.sessions
        assert len(session.messages) == 0

    def test_reuses_existing_session(self, manager):
        """get_or_create_session() sollte existierende Session wiederverwenden."""
        # Create first
        session1 = manager.get_or_create_session("existing-session")
        session1.add_messages([Message(role="user", content="test")])

        # Get again
        session2 = manager.get_or_create_session("existing-session")

        assert session2.session_id == "existing-session"
        assert len(session2.messages) == 1  # Messages preserved

    def test_touches_existing_session(self, manager):
        """get_or_create_session() sollte existierende Session touchen."""
        session1 = manager.get_or_create_session("test-session")
        original_last_accessed = session1.last_accessed

        import time
        time.sleep(0.01)

        session2 = manager.get_or_create_session("test-session")

        assert session2.last_accessed > original_last_accessed

    def test_recreates_expired_session(self, manager):
        """get_or_create_session() sollte expired Session neu erstellen."""
        # Create and expire
        session1 = manager.get_or_create_session("expired-session")
        session1.add_messages([Message(role="user", content="old")])
        session1.expires_at = datetime.utcnow() - timedelta(hours=1)

        # Get again - should recreate
        session2 = manager.get_or_create_session("expired-session")

        assert session2.session_id == "expired-session"
        assert len(session2.messages) == 0  # Messages cleared


# ============================================================================
# Test Class: get_session()
# ============================================================================

class TestGetSession:
    """Tests für get_session()."""

    def test_returns_none_for_nonexistent_session(self, manager):
        """get_session() sollte None für nicht-existierende Session geben."""
        session = manager.get_session("nonexistent")

        assert session is None

    def test_returns_existing_session(self, manager):
        """get_session() sollte existierende Session zurückgeben."""
        manager.get_or_create_session("test-session")

        session = manager.get_session("test-session")

        assert session is not None
        assert session.session_id == "test-session"

    def test_touches_existing_session(self, manager):
        """get_session() sollte existierende Session touchen."""
        session1 = manager.get_or_create_session("test-session")
        original_last_accessed = session1.last_accessed

        import time
        time.sleep(0.01)

        session2 = manager.get_session("test-session")

        assert session2.last_accessed > original_last_accessed

    def test_returns_none_for_expired_session(self, manager):
        """get_session() sollte None für expired Session geben."""
        session = manager.get_or_create_session("test-session")
        session.expires_at = datetime.utcnow() - timedelta(hours=1)

        result = manager.get_session("test-session")

        assert result is None
        assert "test-session" not in manager.sessions  # Should be deleted


# ============================================================================
# Test Class: delete_session()
# ============================================================================

class TestDeleteSession:
    """Tests für delete_session()."""

    def test_deletes_existing_session(self, manager):
        """delete_session() sollte existierende Session löschen."""
        manager.get_or_create_session("test-session")

        result = manager.delete_session("test-session")

        assert result is True
        assert "test-session" not in manager.sessions

    def test_returns_false_for_nonexistent_session(self, manager):
        """delete_session() sollte False für nicht-existierende Session geben."""
        result = manager.delete_session("nonexistent")

        assert result is False


# ============================================================================
# Test Class: list_sessions()
# ============================================================================

class TestListSessions:
    """Tests für list_sessions()."""

    def test_returns_empty_list_when_no_sessions(self, manager):
        """list_sessions() sollte leere Liste ohne Sessions geben."""
        sessions = manager.list_sessions()

        assert sessions == []

    def test_returns_active_sessions(self, manager):
        """list_sessions() sollte aktive Sessions zurückgeben."""
        manager.get_or_create_session("session-1")
        manager.get_or_create_session("session-2")
        manager.get_or_create_session("session-3")

        sessions = manager.list_sessions()

        assert len(sessions) == 3
        session_ids = [s.session_id for s in sessions]
        assert "session-1" in session_ids
        assert "session-2" in session_ids
        assert "session-3" in session_ids

    def test_cleans_up_expired_sessions(self, manager):
        """list_sessions() sollte expired Sessions entfernen."""
        # Create sessions
        manager.get_or_create_session("active-session")
        expired_session = manager.get_or_create_session("expired-session")
        expired_session.expires_at = datetime.utcnow() - timedelta(hours=1)

        sessions = manager.list_sessions()

        assert len(sessions) == 1
        assert sessions[0].session_id == "active-session"
        assert "expired-session" not in manager.sessions


# ============================================================================
# Test Class: process_messages()
# ============================================================================

class TestProcessMessages:
    """Tests für process_messages()."""

    def test_stateless_mode_returns_messages_as_is(self, manager, sample_messages):
        """process_messages() sollte in stateless mode Messages unverändert zurückgeben."""
        all_messages, session_id = manager.process_messages(sample_messages, session_id=None)

        assert all_messages == sample_messages
        assert session_id is None

    def test_session_mode_creates_session(self, manager, sample_messages):
        """process_messages() sollte in session mode Session erstellen."""
        all_messages, session_id = manager.process_messages(
            sample_messages,
            session_id="new-session"
        )

        assert session_id == "new-session"
        assert "new-session" in manager.sessions
        assert len(all_messages) == 3

    def test_session_mode_accumulates_messages(self, manager):
        """process_messages() sollte Messages akkumulieren."""
        # First request - add user message
        messages1 = [Message(role="user", content="Hello")]
        all_messages1, _ = manager.process_messages(messages1, session_id="test-session")
        # WICHTIG: all_messages1 ist REFERENZ zur Session-Liste, nicht Kopie!
        # Daher müssen wir len() sofort checken, nicht später
        first_call_len = len(all_messages1)

        # Second request - add assistant + user
        messages2 = [Message(role="assistant", content="Hi!"), Message(role="user", content="How are you?")]
        all_messages2, _ = manager.process_messages(messages2, session_id="test-session")
        second_call_len = len(all_messages2)

        # process_messages() returns ALL accumulated messages (mutable reference!)
        assert first_call_len == 1  # First call: only 1 message added
        assert second_call_len == 3  # Second call: 1 + 2 = 3 accumulated

        # Verify correct order
        assert all_messages2[0].content == "Hello"
        assert all_messages2[1].content == "Hi!"
        assert all_messages2[2].content == "How are you?"


# ============================================================================
# Test Class: add_assistant_response()
# ============================================================================

class TestAddAssistantResponse:
    """Tests für add_assistant_response()."""

    def test_does_nothing_in_stateless_mode(self, manager):
        """add_assistant_response() sollte in stateless mode nichts tun."""
        response = Message(role="assistant", content="Hello")

        manager.add_assistant_response(session_id=None, assistant_message=response)

        # No exception, no sessions created
        assert len(manager.sessions) == 0

    def test_adds_response_to_existing_session(self, manager):
        """add_assistant_response() sollte Response zu Session hinzufügen."""
        # Create session
        manager.get_or_create_session("test-session")

        # Add response
        response = Message(role="assistant", content="Hello")
        manager.add_assistant_response(session_id="test-session", assistant_message=response)

        # Verify
        session = manager.get_session("test-session")
        assert len(session.messages) == 1
        assert session.messages[0].role == "assistant"


# ============================================================================
# Test Class: get_stats()
# ============================================================================

class TestGetStats:
    """Tests für get_stats()."""

    def test_returns_zero_stats_when_empty(self, manager):
        """get_stats() sollte Nullen ohne Sessions zurückgeben."""
        stats = manager.get_stats()

        assert stats["active_sessions"] == 0
        assert stats["expired_sessions"] == 0
        assert stats["total_messages"] == 0

    def test_returns_correct_stats(self, manager):
        """get_stats() sollte korrekte Stats zurückgeben."""
        # Create active sessions
        session1 = manager.get_or_create_session("session-1")
        session1.add_messages([Message(role="user", content="test1")])

        session2 = manager.get_or_create_session("session-2")
        session2.add_messages([
            Message(role="user", content="test2"),
            Message(role="assistant", content="response2")
        ])

        # Create expired session
        expired_session = manager.get_or_create_session("expired-session")
        expired_session.add_messages([Message(role="user", content="old")])
        expired_session.expires_at = datetime.utcnow() - timedelta(hours=1)

        stats = manager.get_stats()

        assert stats["active_sessions"] == 2
        assert stats["expired_sessions"] == 1
        assert stats["total_messages"] == 4  # 1 + 2 + 1


# ============================================================================
# Test Class: start_cleanup_task()
# ============================================================================

class TestStartCleanupTask:
    """Tests für start_cleanup_task()."""

    @pytest.mark.asyncio
    async def test_starts_cleanup_task(self, manager):
        """start_cleanup_task() sollte cleanup task starten."""
        manager.start_cleanup_task()

        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        # Cleanup
        manager.shutdown()

    @pytest.mark.asyncio
    async def test_does_not_restart_if_already_running(self, manager):
        """start_cleanup_task() sollte nicht neustarten wenn schon läuft."""
        manager.start_cleanup_task()
        first_task = manager._cleanup_task

        manager.start_cleanup_task()
        second_task = manager._cleanup_task

        assert first_task is second_task

        # Cleanup
        manager.shutdown()


# ============================================================================
# Test Class: shutdown()
# ============================================================================

class TestShutdown:
    """Tests für shutdown()."""

    @pytest.mark.asyncio
    async def test_cancels_cleanup_task(self, manager):
        """shutdown() sollte cleanup task canceln."""
        manager.start_cleanup_task()

        manager.shutdown()

        # Task should be cancelled
        await asyncio.sleep(0.01)  # Give it time to cancel
        assert manager._cleanup_task.cancelled()

    def test_clears_sessions(self, manager):
        """shutdown() sollte alle Sessions löschen."""
        manager.get_or_create_session("session-1")
        manager.get_or_create_session("session-2")

        manager.shutdown()

        assert len(manager.sessions) == 0


# ============================================================================
# Test Summary
# ============================================================================

"""
Test Summary für session_manager.py:

✅ Test Coverage:
- Session dataclass (10 Tests) - creation, touch, add_messages, expiration, to_session_info
- SessionManager.__init__() (2 Tests) - default + custom values
- get_or_create_session() (4 Tests) - create, reuse, touch, recreate expired
- get_session() (4 Tests) - get existing, touch, return None, delete expired
- delete_session() (2 Tests) - delete existing, return False for nonexistent
- list_sessions() (3 Tests) - empty, active, cleanup expired
- process_messages() (3 Tests) - stateless mode, session creation, accumulation
- add_assistant_response() (2 Tests) - stateless mode, add to session
- get_stats() (2 Tests) - zero stats, correct stats
- start_cleanup_task() (2 Tests) - start task, no restart
- shutdown() (2 Tests) - cancel task, clear sessions

Total: 36 Tests

🎯 Test Strategy:
- Time-sensitive tests verwenden kleine Delays (0.01s)
- Expired sessions werden durch Setzen von expires_at in Vergangenheit simuliert
- Thread-safe operations werden durch Lock implizit getestet
- Async cleanup task wird gestartet und sauber beendet
"""
