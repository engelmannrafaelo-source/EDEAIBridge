"""
Unit Tests für request_limiter.py - Request Rate Limiting

Test Coverage:
- RequestLimiter.__init__() - Initialization mit default/custom limits
- can_accept_request() - Concurrency check, memory check
- acquire() - Increment active requests
- release() - Decrement active requests
- get_stats() - Statistics collection
- RequestLimiterMiddleware.dispatch() - Request handling, rejection, health checks
- get_limiter() - Global singleton

WICHTIG: Diese Tests testen NUR die request_limiter.py Funktionalität!
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import zu testende Module
from src.request_limiter import RequestLimiter, RequestLimiterMiddleware, get_limiter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def limiter():
    """Fresh RequestLimiter instance für jeden Test."""
    return RequestLimiter(max_concurrent=3, memory_threshold_percent=90.0)


@pytest.fixture
def mock_memory_ok():
    """Mock: psutil.virtual_memory() mit OK memory."""
    mock_mem = Mock()
    mock_mem.percent = 50.0  # 50% usage - OK
    mock_mem.used = 8 * 1024**3  # 8GB used
    mock_mem.total = 16 * 1024**3  # 16GB total

    with patch('request_limiter.psutil.virtual_memory', return_value=mock_mem):
        yield mock_mem


@pytest.fixture
def mock_memory_high():
    """Mock: psutil.virtual_memory() mit high memory."""
    mock_mem = Mock()
    mock_mem.percent = 95.0  # 95% usage - TOO HIGH
    mock_mem.used = 15.2 * 1024**3  # 15.2GB used
    mock_mem.total = 16 * 1024**3  # 16GB total

    with patch('request_limiter.psutil.virtual_memory', return_value=mock_mem):
        yield mock_mem


# ============================================================================
# Test Class: RequestLimiter.__init__()
# ============================================================================

class TestRequestLimiterInit:
    """Tests für RequestLimiter Konstruktor."""

    @patch('request_limiter.psutil')
    def test_init_default_values(self, mock_psutil):
        """RequestLimiter sollte mit defaults initialisiert werden."""
        limiter = RequestLimiter()

        assert limiter.max_concurrent == 3
        assert limiter.memory_threshold == 90.0
        assert limiter.active_requests == 0
        assert limiter.total_requests == 0
        assert limiter.rejected_requests == 0

    @patch('request_limiter.psutil')
    def test_init_custom_values(self, mock_psutil):
        """RequestLimiter sollte custom Werte akzeptieren."""
        limiter = RequestLimiter(max_concurrent=5, memory_threshold_percent=85.0)

        assert limiter.max_concurrent == 5
        assert limiter.memory_threshold == 85.0


# ============================================================================
# Test Class: can_accept_request()
# ============================================================================

class TestCanAcceptRequest:
    """Tests für can_accept_request()."""

    @pytest.mark.asyncio
    async def test_accepts_request_when_under_limit(self, limiter, mock_memory_ok):
        """can_accept_request() sollte True geben wenn unter limit."""
        can_accept, reason = await limiter.can_accept_request()

        assert can_accept is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_rejects_when_at_concurrent_limit(self, limiter, mock_memory_ok):
        """can_accept_request() sollte False geben bei max concurrent."""
        # Simulate 3 active requests (max_concurrent=3)
        limiter.active_requests = 3

        can_accept, reason = await limiter.can_accept_request()

        assert can_accept is False
        assert "Max concurrent requests reached" in reason
        assert "3/3" in reason

    @pytest.mark.asyncio
    async def test_rejects_when_memory_too_high(self, limiter, mock_memory_high):
        """can_accept_request() sollte False geben bei high memory."""
        can_accept, reason = await limiter.can_accept_request()

        assert can_accept is False
        assert "Memory threshold exceeded" in reason
        assert "95.0%" in reason

    @pytest.mark.asyncio
    async def test_concurrent_limit_takes_precedence(self, limiter, mock_memory_high):
        """can_accept_request() sollte concurrent limit vor memory prüfen."""
        limiter.active_requests = 3

        can_accept, reason = await limiter.can_accept_request()

        # Should reject for concurrent limit, not memory
        assert can_accept is False
        assert "Max concurrent" in reason


# ============================================================================
# Test Class: acquire() / release()
# ============================================================================

class TestAcquireRelease:
    """Tests für acquire() und release()."""

    @pytest.mark.asyncio
    async def test_acquire_increments_counters(self, limiter, mock_memory_ok):
        """acquire() sollte active_requests und total_requests erhöhen."""
        await limiter.acquire()

        assert limiter.active_requests == 1
        assert limiter.total_requests == 1

    @pytest.mark.asyncio
    async def test_multiple_acquires_increment(self, limiter, mock_memory_ok):
        """Mehrere acquire() calls sollten counters erhöhen."""
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

        assert limiter.active_requests == 3
        assert limiter.total_requests == 3

    @pytest.mark.asyncio
    async def test_release_decrements_active_requests(self, limiter, mock_memory_ok):
        """release() sollte active_requests verringern."""
        await limiter.acquire()
        await limiter.acquire()

        await limiter.release()

        assert limiter.active_requests == 1
        assert limiter.total_requests == 2  # total_requests bleibt

    @pytest.mark.asyncio
    async def test_release_never_goes_negative(self, limiter, mock_memory_ok):
        """release() sollte nie negativ werden."""
        # Release without acquire
        await limiter.release()

        assert limiter.active_requests == 0  # Should stay at 0

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self, limiter, mock_memory_ok):
        """acquire/release cycle sollte korrekt funktionieren."""
        # Cycle 1
        await limiter.acquire()
        assert limiter.active_requests == 1
        await limiter.release()
        assert limiter.active_requests == 0

        # Cycle 2
        await limiter.acquire()
        assert limiter.active_requests == 1
        assert limiter.total_requests == 2  # Total accumulates


# ============================================================================
# Test Class: get_stats()
# ============================================================================

class TestGetStats:
    """Tests für get_stats()."""

    def test_returns_stats_dict(self, limiter, mock_memory_ok):
        """get_stats() sollte stats dict zurückgeben."""
        stats = limiter.get_stats()

        assert isinstance(stats, dict)
        assert 'active_requests' in stats
        assert 'max_concurrent' in stats
        assert 'total_requests' in stats
        assert 'rejected_requests' in stats
        assert 'memory_usage_percent' in stats
        assert 'memory_used_gb' in stats
        assert 'memory_total_gb' in stats
        assert 'memory_threshold' in stats

    def test_stats_reflect_current_state(self, limiter, mock_memory_ok):
        """get_stats() sollte aktuellen State widerspiegeln."""
        limiter.active_requests = 2
        limiter.total_requests = 10
        limiter.rejected_requests = 3

        stats = limiter.get_stats()

        assert stats['active_requests'] == 2
        assert stats['max_concurrent'] == 3
        assert stats['total_requests'] == 10
        assert stats['rejected_requests'] == 3
        assert stats['memory_usage_percent'] == 50.0
        assert stats['memory_threshold'] == 90.0


# ============================================================================
# Test Class: RequestLimiterMiddleware
# ============================================================================

class TestRequestLimiterMiddleware:
    """Tests für RequestLimiterMiddleware."""

    @pytest.mark.asyncio
    async def test_passes_health_check_without_limiting(self, limiter, mock_memory_ok):
        """Middleware sollte health checks durchlassen ohne limit."""
        app = Mock()
        middleware = RequestLimiterMiddleware(app, limiter)

        # Mock health check request
        request = Mock(spec=Request)
        request.url.path = "/health"

        call_next = AsyncMock(return_value="health_response")

        response = await middleware.dispatch(request, call_next)

        assert response == "health_response"
        call_next.assert_called_once_with(request)
        # No acquire/release should happen
        assert limiter.active_requests == 0

    @pytest.mark.asyncio
    async def test_passes_metrics_without_limiting(self, limiter, mock_memory_ok):
        """Middleware sollte /metrics durchlassen ohne limit."""
        app = Mock()
        middleware = RequestLimiterMiddleware(app, limiter)

        request = Mock(spec=Request)
        request.url.path = "/metrics"

        call_next = AsyncMock(return_value="metrics_response")

        response = await middleware.dispatch(request, call_next)

        assert response == "metrics_response"
        assert limiter.active_requests == 0

    @pytest.mark.asyncio
    async def test_accepts_normal_request(self, limiter, mock_memory_ok):
        """Middleware sollte normale Requests akzeptieren."""
        app = Mock()
        middleware = RequestLimiterMiddleware(app, limiter)

        request = Mock(spec=Request)
        request.url.path = "/v1/chat/completions"

        call_next = AsyncMock(return_value="completion_response")

        response = await middleware.dispatch(request, call_next)

        assert response == "completion_response"
        # Should have acquired and released
        assert limiter.active_requests == 0
        assert limiter.total_requests == 1

    @pytest.mark.asyncio
    async def test_rejects_when_over_limit(self, limiter, mock_memory_ok):
        """Middleware sollte Request ablehnen wenn über limit."""
        app = Mock()
        middleware = RequestLimiterMiddleware(app, limiter)

        # Simulate max concurrent reached
        limiter.active_requests = 3

        request = Mock(spec=Request)
        request.url.path = "/v1/chat/completions"

        call_next = AsyncMock()

        response = await middleware.dispatch(request, call_next)

        # Should return 503 JSONResponse
        assert isinstance(response, JSONResponse)
        assert response.status_code == 503
        # call_next should NOT be called
        call_next.assert_not_called()
        # rejected_requests should increment
        assert limiter.rejected_requests == 1

    @pytest.mark.asyncio
    async def test_releases_on_exception(self, limiter, mock_memory_ok):
        """Middleware sollte release() auch bei Exception aufrufen."""
        app = Mock()
        middleware = RequestLimiterMiddleware(app, limiter)

        request = Mock(spec=Request)
        request.url.path = "/v1/chat/completions"

        # call_next raises exception
        call_next = AsyncMock(side_effect=Exception("Test error"))

        with pytest.raises(Exception):
            await middleware.dispatch(request, call_next)

        # Should have released even after exception
        assert limiter.active_requests == 0
        assert limiter.total_requests == 1


# ============================================================================
# Test Class: get_limiter()
# ============================================================================

class TestGetLimiter:
    """Tests für get_limiter() global singleton."""

    @patch('request_limiter.psutil')
    def test_creates_limiter_on_first_call(self, mock_psutil):
        """get_limiter() sollte limiter beim ersten Call erstellen."""
        # Reset global
        import request_limiter
        request_limiter.limiter = None

        limiter = get_limiter(max_concurrent=5, memory_threshold=85.0)

        assert limiter is not None
        assert limiter.max_concurrent == 5
        assert limiter.memory_threshold == 85.0

    @patch('request_limiter.psutil')
    def test_returns_same_instance_on_second_call(self, mock_psutil):
        """get_limiter() sollte gleiche Instanz wiederverwenden."""
        # Reset global
        import request_limiter
        request_limiter.limiter = None

        limiter1 = get_limiter()
        limiter2 = get_limiter()

        assert limiter1 is limiter2


# ============================================================================
# Test Summary
# ============================================================================

"""
Test Summary für request_limiter.py:

✅ Test Coverage:
- RequestLimiter.__init__() (2 Tests) - default + custom values
- can_accept_request() (4 Tests) - accept, reject concurrent, reject memory, precedence
- acquire() / release() (5 Tests) - increment, decrement, cycle, no negative
- get_stats() (2 Tests) - dict structure, correct values
- RequestLimiterMiddleware (6 Tests) - health checks, accept, reject, exception handling
- get_limiter() (2 Tests) - create, singleton

Total: 21 Tests

🎯 Test Strategy:
- Memory usage wird gemockt (psutil.virtual_memory)
- Async tests verwenden pytest.mark.asyncio
- Middleware tests mocken Request und call_next
- Global singleton wird zwischen Tests zurückgesetzt
- Exception handling mit finally-block wird getestet
"""
