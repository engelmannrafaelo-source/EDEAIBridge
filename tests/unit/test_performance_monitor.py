"""
Unit Tests für middleware/performance_monitor.py - Performance Monitoring

Test Coverage:
- PerformanceMonitorMiddleware - ASGI middleware für Performance-Tracking
- RequestMetrics - Metrics collection und aggregation
- Threshold Configuration - Tool-aware und non-tool thresholds
- Tool Detection - enable_tools parsing from request body
- Logging - Slow/very slow request warnings
- Metrics Recording - Duration tracking und aggregation

WICHTIG: Diese Tests testen NUR die performance_monitor.py!
"""

import pytest
import time
import json
from unittest.mock import Mock, AsyncMock, patch, call
from typing import Dict, List

# Import zu testende Module
from middleware.performance_monitor import (
    PerformanceMonitorMiddleware,
    RequestMetrics,
    metrics
)


# ============================================================================
# Test Class: RequestMetrics
# ============================================================================

class TestRequestMetrics:
    """Tests für RequestMetrics class."""

    @pytest.fixture
    def metrics(self):
        """Fixture: Neue RequestMetrics Instanz."""
        return RequestMetrics()

    def test_creates_empty_metrics(self, metrics):
        """RequestMetrics sollte mit leeren Werten initialisiert werden."""
        assert metrics.request_count == 0
        assert metrics.total_duration == 0.0
        assert metrics.slow_requests == 0
        assert metrics.very_slow_requests == 0
        assert metrics.endpoint_metrics == {}

    def test_records_fast_request(self, metrics):
        """record_request() sollte normale requests tracken."""
        metrics.record_request(
            endpoint="/v1/chat/completions",
            duration=2.5,
            slow_threshold=5.0,
            very_slow_threshold=10.0
        )

        assert metrics.request_count == 1
        assert metrics.total_duration == 2.5
        assert metrics.slow_requests == 0
        assert metrics.very_slow_requests == 0
        assert "/v1/chat/completions" in metrics.endpoint_metrics

    def test_records_slow_request(self, metrics):
        """record_request() sollte slow requests markieren."""
        metrics.record_request(
            endpoint="/v1/chat/completions",
            duration=6.0,
            slow_threshold=5.0,
            very_slow_threshold=10.0
        )

        assert metrics.request_count == 1
        assert metrics.slow_requests == 1
        assert metrics.very_slow_requests == 0

    def test_records_very_slow_request(self, metrics):
        """record_request() sollte very slow requests markieren."""
        metrics.record_request(
            endpoint="/v1/chat/completions",
            duration=12.0,
            slow_threshold=5.0,
            very_slow_threshold=10.0
        )

        assert metrics.request_count == 1
        assert metrics.slow_requests == 0  # Not counted as slow
        assert metrics.very_slow_requests == 1

    def test_tracks_endpoint_metrics(self, metrics):
        """record_request() sollte per-endpoint metrics tracken."""
        metrics.record_request("/v1/chat/completions", 2.0)
        metrics.record_request("/v1/chat/completions", 4.0)
        metrics.record_request("/v1/models", 1.0)

        endpoint_data = metrics.endpoint_metrics["/v1/chat/completions"]
        assert endpoint_data['count'] == 2
        assert endpoint_data['total_duration'] == 6.0
        assert endpoint_data['min_duration'] == 2.0
        assert endpoint_data['max_duration'] == 4.0

        models_data = metrics.endpoint_metrics["/v1/models"]
        assert models_data['count'] == 1

    def test_get_summary_empty(self, metrics):
        """get_summary() sollte mit 0 requests funktionieren."""
        summary = metrics.get_summary()

        assert summary['total_requests'] == 0
        assert summary['average_duration'] == 0.0
        assert summary['slow_requests'] == 0
        assert summary['endpoints'] == {}

    def test_get_summary_with_data(self, metrics):
        """get_summary() sollte aggregierte stats zurückgeben."""
        metrics.record_request("/v1/chat/completions", 2.0)
        metrics.record_request("/v1/chat/completions", 4.0)
        metrics.record_request("/v1/models", 1.0)

        summary = metrics.get_summary()

        assert summary['total_requests'] == 3
        assert summary['average_duration'] == 2.333  # (2 + 4 + 1) / 3
        assert "/v1/chat/completions" in summary['endpoints']
        assert summary['endpoints']["/v1/chat/completions"]['count'] == 2
        assert summary['endpoints']["/v1/chat/completions"]['avg_duration'] == 3.0

    def test_log_summary(self, metrics, caplog):
        """log_summary() sollte summary loggen."""
        import logging
        caplog.set_level(logging.INFO, logger="middleware.performance_monitor")

        metrics.record_request("/v1/chat/completions", 2.0)
        metrics.log_summary()

        assert "Performance Summary" in caplog.text
        assert "total_requests" in caplog.text


# ============================================================================
# Test Class: PerformanceMonitorMiddleware - Configuration
# ============================================================================

class TestPerformanceMonitorMiddlewareConfig:
    """Tests für PerformanceMonitorMiddleware configuration."""

    def test_initializes_with_defaults(self):
        """Middleware sollte mit default thresholds initialisiert werden."""
        app = Mock()

        with patch.dict('os.environ', {}, clear=False):
            middleware = PerformanceMonitorMiddleware(app)

        assert middleware.slow_threshold == 5.0
        assert middleware.very_slow_threshold == 10.0
        assert middleware.slow_threshold_tools == 30.0
        assert middleware.very_slow_threshold_tools == 60.0

    def test_loads_custom_thresholds_from_env(self):
        """Middleware sollte custom thresholds aus env laden."""
        app = Mock()

        env_vars = {
            'SLOW_REQUEST_THRESHOLD': '3.0',
            'VERY_SLOW_REQUEST_THRESHOLD': '8.0',
            'SLOW_REQUEST_THRESHOLD_TOOLS': '20.0',
            'VERY_SLOW_REQUEST_THRESHOLD_TOOLS': '40.0'
        }

        with patch.dict('os.environ', env_vars, clear=False):
            middleware = PerformanceMonitorMiddleware(app)

        assert middleware.slow_threshold == 3.0
        assert middleware.very_slow_threshold == 8.0
        assert middleware.slow_threshold_tools == 20.0
        assert middleware.very_slow_threshold_tools == 40.0


# ============================================================================
# Test Class: PerformanceMonitorMiddleware - ASGI
# ============================================================================

class TestPerformanceMonitorMiddlewareASGI:
    """Tests für PerformanceMonitorMiddleware ASGI behavior."""

    @pytest.fixture
    def app(self):
        """Fixture: Mock ASGI app."""
        app = AsyncMock()
        return app

    @pytest.fixture
    def middleware(self, app):
        """Fixture: PerformanceMonitorMiddleware instance."""
        with patch.dict('os.environ', {
            'SLOW_REQUEST_THRESHOLD': '5.0',
            'VERY_SLOW_REQUEST_THRESHOLD': '10.0'
        }, clear=False):
            return PerformanceMonitorMiddleware(app)

    @pytest.fixture
    def http_scope(self):
        """Fixture: Basic HTTP scope."""
        return {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "client": ("127.0.0.1", 8000)
        }

    @pytest.mark.asyncio
    async def test_passes_non_http_requests(self, middleware, app):
        """Middleware sollte non-HTTP requests unverändert durchlassen."""
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_tracks_request_duration(self, middleware, app, http_scope, caplog):
        """Middleware sollte request duration tracken."""
        import logging
        caplog.set_level(logging.INFO, logger="middleware.performance_monitor")

        receive = AsyncMock(return_value={"type": "http.request", "body": b"", "more_body": False})
        send = AsyncMock()

        # Mock app to send response
        async def mock_app(scope, recv, snd):
            await snd({"type": "http.response.start", "status": 200})
            await snd({"type": "http.response.body", "body": b"OK", "more_body": False})

        middleware.app = mock_app

        await middleware(http_scope, receive, send)

        # Check logging
        assert "Request completed" in caplog.text
        assert "GET /health" in caplog.text

    @pytest.mark.asyncio
    async def test_detects_tool_usage_from_body(self, middleware, app, caplog):
        """Middleware sollte enable_tools aus request body erkennen."""
        import logging
        caplog.set_level(logging.DEBUG, logger="middleware.performance_monitor")

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "client": ("127.0.0.1", 8000)
        }

        request_body = json.dumps({
            "model": "claude-sonnet-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "enable_tools": True
        }).encode()

        receive = AsyncMock(return_value={
            "type": "http.request",
            "body": request_body,
            "more_body": False
        })
        send = AsyncMock()

        # Mock app to send response
        async def mock_app(scope, recv, snd):
            await recv()  # Trigger receive
            await snd({"type": "http.response.start", "status": 200})
            await snd({"type": "http.response.body", "body": b"OK", "more_body": False})

        middleware.app = mock_app

        await middleware(scope, receive, send)

        # Check tool detection
        assert "Tool usage detected" in caplog.text

    @pytest.mark.asyncio
    async def test_logs_slow_request_warning(self, middleware, app, http_scope, caplog):
        """Middleware sollte slow request warnings loggen."""
        import logging
        caplog.set_level(logging.WARNING, logger="middleware.performance_monitor")

        receive = AsyncMock(return_value={"type": "http.request", "body": b"", "more_body": False})
        send = AsyncMock()

        # Mock app to send response
        async def slow_app(scope, recv, snd):
            await snd({"type": "http.response.start", "status": 200})
            await snd({"type": "http.response.body", "body": b"OK", "more_body": False})

        middleware.app = slow_app

        # Mock time.time for duration calculation (6 seconds > 5.0 slow threshold)
        # Start time: 0.0, end time: 6.0
        with patch('middleware.performance_monitor.time.time', side_effect=[0.0, 6.0]):
            await middleware(http_scope, receive, send)

        # Check warning
        assert "Slow request" in caplog.text

    @pytest.mark.asyncio
    async def test_logs_very_slow_request_error(self, middleware, app, http_scope, caplog):
        """Middleware sollte very slow request errors loggen."""
        import logging
        caplog.set_level(logging.ERROR, logger="middleware.performance_monitor")

        receive = AsyncMock(return_value={"type": "http.request", "body": b"", "more_body": False})
        send = AsyncMock()

        # Mock app to send response
        async def very_slow_app(scope, recv, snd):
            await snd({"type": "http.response.start", "status": 200})
            await snd({"type": "http.response.body", "body": b"OK", "more_body": False})

        middleware.app = very_slow_app

        # Mock time.time for duration calculation (12 seconds > 10.0 very slow)
        with patch('middleware.performance_monitor.time.time', side_effect=[0.0, 12.0]):
            await middleware(http_scope, receive, send)

        # Check error
        assert "VERY SLOW REQUEST" in caplog.text

    @pytest.mark.asyncio
    async def test_logs_request_exception(self, middleware, app, http_scope, caplog):
        """Middleware sollte exceptions mit duration loggen."""
        import logging
        caplog.set_level(logging.ERROR, logger="middleware.performance_monitor")

        receive = AsyncMock(return_value={"type": "http.request", "body": b"", "more_body": False})
        send = AsyncMock()

        # Mock app to raise exception
        async def failing_app(scope, recv, snd):
            raise ValueError("Test error")

        middleware.app = failing_app

        with pytest.raises(ValueError):
            await middleware(http_scope, receive, send)

        # Check error logging
        assert "Request failed" in caplog.text
        assert "ValueError" in caplog.text


# ============================================================================
# Test Class: Global Metrics Instance
# ============================================================================

class TestGlobalMetrics:
    """Tests für global metrics instance."""

    def test_global_metrics_exists(self):
        """Global metrics instance sollte existieren."""
        from middleware.performance_monitor import metrics

        assert metrics is not None
        assert isinstance(metrics, RequestMetrics)


# ============================================================================
# Test Summary
# ============================================================================

"""
Test Summary für middleware/performance_monitor.py:

✅ Test Coverage:
- RequestMetrics (7 Tests) - initialization, recording, aggregation, summary
- PerformanceMonitorMiddleware Config (2 Tests) - defaults, env loading
- PerformanceMonitorMiddleware ASGI (7 Tests) - HTTP handling, duration tracking, tool detection, slow/very slow logging, exceptions
- Global Metrics (1 Test) - instance existence

Total: 17 Tests

🎯 Test Strategy:
- RequestMetrics: Unit tests für metrics collection und aggregation
- Middleware: ASGI behavior testing mit mocked app/receive/send
- Tool Detection: Body parsing for enable_tools field
- Threshold Testing: Slow/very slow warnings based on thresholds
- Exception Handling: Request failure logging with duration
- Time Mocking: patch time.time for duration simulation

📝 Key Patterns:
- AsyncMock für ASGI app/receive/send
- patch time.time für duration control
- caplog für log verification
- Environment variable patching für config tests
"""
