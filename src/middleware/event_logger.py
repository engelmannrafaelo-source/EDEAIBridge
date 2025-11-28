"""
Structured Event Logging for Analytics.

Provides structured event logging for business logic tracking and analytics.
Events are logged in JSON format for easy parsing and analysis.

Events tracked:
- User authentication events
- Chat completion events
- Session management events
- Error events
- Performance events

Usage:
    from middleware.event_logger import EventLogger, log_event

    log_event("chat_completion", {
        "session_id": "abc123",
        "model": "claude-sonnet-4",
        "tokens": 150
    })
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime
from config.logging_config import get_logger

logger = get_logger(__name__)


class EventLogger:
    """
    Structured event logger for analytics and monitoring.

    Logs events in JSON format with standardized fields:
    - timestamp: ISO 8601 timestamp
    - event_type: Type of event (e.g., "chat_completion")
    - data: Event-specific data
    - metadata: Additional context (optional)
    """

    @staticmethod
    def log_event(
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        level: str = "INFO"
    ):
        """
        Log a structured event.

        Args:
            event_type: Type of event (e.g., "chat_completion", "user_auth")
            data: Event-specific data dictionary
            metadata: Optional metadata (user_agent, ip_address, etc.)
            level: Log level (INFO, WARNING, ERROR)
        """
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "data": data
        }

        if metadata:
            event["metadata"] = metadata

        # Log as JSON string
        event_json = json.dumps(event)

        # Log at appropriate level
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(f"EVENT: {event_json}")

    @staticmethod
    def log_chat_completion(
        session_id: str,
        model: str,
        message_count: int,
        stream: bool,
        duration: Optional[float] = None,
        tokens: Optional[int] = None,
        error: Optional[str] = None,
        tools_enabled: Optional[bool] = None
    ):
        """
        Log chat completion event.

        Args:
            session_id: Session identifier
            model: Model used
            message_count: Number of messages
            stream: Whether streaming was used
            duration: Request duration in seconds
            tokens: Token count
            error: Error message if failed
            tools_enabled: Whether tools were enabled for this request
        """
        data = {
            "session_id": session_id,
            "model": model,
            "message_count": message_count,
            "stream": stream
        }

        if duration is not None:
            data["duration_seconds"] = round(duration, 3)

        if tokens is not None:
            data["tokens"] = tokens

        if tools_enabled is not None:
            data["tools_enabled"] = tools_enabled

        if error:
            data["error"] = error
            EventLogger.log_event("chat_completion_error", data, level="ERROR")
        else:
            EventLogger.log_event("chat_completion", data)

    @staticmethod
    def log_authentication(
        success: bool,
        method: str = "api_key",
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log authentication event."""
        data = {
            "success": success,
            "method": method
        }

        if error:
            data["error"] = error

        level = "INFO" if success else "WARNING"
        EventLogger.log_event("authentication", data, metadata=metadata, level=level)

    @staticmethod
    def log_session_event(
        event_subtype: str,
        session_id: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log session management event.

        Args:
            event_subtype: created, updated, deleted, expired
            session_id: Session identifier
            details: Additional session details
        """
        data = {
            "subtype": event_subtype,
            "session_id": session_id
        }

        if details:
            data.update(details)

        EventLogger.log_event("session_management", data)

    @staticmethod
    def log_rate_limit_event(
        endpoint: str,
        limit: int,
        window: str,
        exceeded: bool = False
    ):
        """Log rate limiting event."""
        data = {
            "endpoint": endpoint,
            "limit": limit,
            "window": window,
            "exceeded": exceeded
        }

        level = "WARNING" if exceeded else "INFO"
        EventLogger.log_event("rate_limit", data, level=level)

    @staticmethod
    def log_error_event(
        error_type: str,
        error_message: str,
        endpoint: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log error event."""
        data = {
            "error_type": error_type,
            "error_message": error_message
        }

        if endpoint:
            data["endpoint"] = endpoint

        EventLogger.log_event("error", data, metadata=metadata, level="ERROR")


# Convenience function for quick event logging
def log_event(event_type: str, data: Dict[str, Any], **kwargs):
    """
    Convenience function for logging events.

    Args:
        event_type: Type of event
        data: Event data
        **kwargs: Additional arguments (metadata, level)
    """
    EventLogger.log_event(event_type, data, **kwargs)
