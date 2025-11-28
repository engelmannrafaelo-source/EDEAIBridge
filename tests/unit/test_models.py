"""
Unit Tests für models.py - Pydantic Models & Validation

Test Coverage:
- ContentPart - Text content parts
- Message - Message model mit content normalization
- ChatCompletionRequest - Request validation, field validators, to_claude_options()
- ChatCompletionResponse - Response model generation
- ChatCompletionStreamResponse - Stream response model
- Choice, StreamChoice, Usage - Helper models
- ErrorDetail, ErrorResponse - Error models
- SessionInfo, SessionListResponse - Session models

WICHTIG: Diese Tests testen NUR die models.py Pydantic Models!
"""

import pytest
from datetime import datetime
from typing import List
from pydantic import ValidationError

# Import zu testende Module
from src.models import (
    ContentPart,
    Message,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    Choice,
    StreamChoice,
    Usage,
    ErrorDetail,
    ErrorResponse,
    SessionInfo,
    SessionListResponse
)


# ============================================================================
# Test Class: ContentPart
# ============================================================================

class TestContentPart:
    """Tests für ContentPart model."""

    def test_creates_valid_content_part(self):
        """ContentPart sollte mit valid data erstellt werden."""
        part = ContentPart(type="text", text="Hello world")

        assert part.type == "text"
        assert part.text == "Hello world"

    def test_requires_type_and_text(self):
        """ContentPart sollte type und text erfordern."""
        with pytest.raises(ValidationError):
            ContentPart()


# ============================================================================
# Test Class: Message
# ============================================================================

class TestMessage:
    """Tests für Message model mit content normalization."""

    def test_creates_message_with_string_content(self):
        """Message sollte mit string content erstellt werden."""
        msg = Message(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.name is None

    def test_creates_message_with_name(self):
        """Message sollte optional name akzeptieren."""
        msg = Message(role="user", content="Hello", name="John")

        assert msg.name == "John"

    def test_normalizes_array_content_to_string(self):
        """Message sollte array content zu string konvertieren."""
        msg = Message(
            role="user",
            content=[
                ContentPart(type="text", text="First part"),
                ContentPart(type="text", text="Second part")
            ]
        )

        # Should be normalized to string with newlines
        assert isinstance(msg.content, str)
        assert msg.content == "First part\nSecond part"

    def test_normalizes_dict_content_to_string(self):
        """Message sollte dict content zu string konvertieren."""
        msg = Message(
            role="user",
            content=[
                {"type": "text", "text": "Part one"},
                {"type": "text", "text": "Part two"}
            ]
        )

        assert isinstance(msg.content, str)
        assert msg.content == "Part one\nPart two"

    def test_handles_empty_content_array(self):
        """Message sollte leeres content array zu empty string konvertieren."""
        msg = Message(role="user", content=[])

        assert msg.content == ""

    def test_validates_role_enum(self):
        """Message sollte nur valid roles akzeptieren."""
        with pytest.raises(ValidationError):
            Message(role="invalid", content="Hello")


# ============================================================================
# Test Class: ChatCompletionRequest
# ============================================================================

class TestChatCompletionRequest:
    """Tests für ChatCompletionRequest validation."""

    def test_creates_minimal_request(self):
        """ChatCompletionRequest sollte mit minimal data erstellt werden."""
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")]
        )

        assert req.model == "claude-sonnet-4"
        assert len(req.messages) == 1
        assert req.stream is False
        assert req.temperature == 1.0

    def test_default_values(self):
        """ChatCompletionRequest sollte korrekte defaults haben."""
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")]
        )

        assert req.temperature == 1.0
        assert req.top_p == 1.0
        assert req.n == 1
        assert req.stream is False
        assert req.presence_penalty == 0
        assert req.frequency_penalty == 0
        assert req.session_id is None
        assert req.enable_tools is False

    def test_validates_n_equals_1(self):
        """ChatCompletionRequest sollte n=1 erlauben."""
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            n=1
        )

        assert req.n == 1

    def test_rejects_n_greater_than_1(self):
        """ChatCompletionRequest sollte n>1 ablehnen."""
        with pytest.raises(ValidationError) as exc_info:
            ChatCompletionRequest(
                model="claude-sonnet-4",
                messages=[Message(role="user", content="Hello")],
                n=2
            )

        assert "multiple choices" in str(exc_info.value).lower()

    def test_validates_temperature_range(self):
        """ChatCompletionRequest sollte temperature range validieren."""
        # Valid
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            temperature=0.5
        )
        assert req.temperature == 0.5

        # Invalid - too high
        with pytest.raises(ValidationError):
            ChatCompletionRequest(
                model="claude-sonnet-4",
                messages=[Message(role="user", content="Hello")],
                temperature=3.0
            )

        # Invalid - negative
        with pytest.raises(ValidationError):
            ChatCompletionRequest(
                model="claude-sonnet-4",
                messages=[Message(role="user", content="Hello")],
                temperature=-0.5
            )

    def test_validates_top_p_range(self):
        """ChatCompletionRequest sollte top_p range validieren."""
        # Valid
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            top_p=0.9
        )
        assert req.top_p == 0.9

        # Invalid
        with pytest.raises(ValidationError):
            ChatCompletionRequest(
                model="claude-sonnet-4",
                messages=[Message(role="user", content="Hello")],
                top_p=1.5
            )

    def test_accepts_session_id(self):
        """ChatCompletionRequest sollte session_id akzeptieren."""
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            session_id="session-123"
        )

        assert req.session_id == "session-123"

    def test_accepts_enable_tools(self):
        """ChatCompletionRequest sollte enable_tools akzeptieren."""
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            enable_tools=True
        )

        assert req.enable_tools is True

    def test_log_unsupported_parameters(self, caplog):
        """log_unsupported_parameters() sollte warnings loggen."""
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            temperature=0.7,
            max_tokens=100,
            stop=["STOP"]
        )

        req.log_unsupported_parameters()

        # Check warnings were logged
        assert "temperature=0.7" in caplog.text
        assert "max_tokens=100" in caplog.text
        assert "stop sequences" in caplog.text

    def test_to_claude_options_includes_model(self, caplog):
        """to_claude_options() sollte model inkludieren."""
        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")]
        )

        options = req.to_claude_options()

        assert "model" in options
        assert options["model"] == "claude-sonnet-4"

    def test_to_claude_options_logs_user(self, caplog):
        """to_claude_options() sollte user field loggen."""
        import logging
        caplog.set_level(logging.INFO, logger="models")

        req = ChatCompletionRequest(
            model="claude-sonnet-4",
            messages=[Message(role="user", content="Hello")],
            user="user-123"
        )

        options = req.to_claude_options()

        # Check if user was logged (INFO level)
        assert any("user-123" in record.message for record in caplog.records if record.levelname == "INFO")


# ============================================================================
# Test Class: ChatCompletionResponse
# ============================================================================

class TestChatCompletionResponse:
    """Tests für ChatCompletionResponse model."""

    def test_creates_response_with_defaults(self):
        """ChatCompletionResponse sollte mit auto-generated defaults erstellt werden."""
        response = ChatCompletionResponse(
            model="claude-sonnet-4",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content="Hello!"),
                    finish_reason="stop"
                )
            ]
        )

        # Auto-generated fields
        assert response.id.startswith("chatcmpl-")
        assert response.object == "chat.completion"
        assert isinstance(response.created, int)
        assert response.model == "claude-sonnet-4"
        assert len(response.choices) == 1

    def test_includes_usage_when_provided(self):
        """ChatCompletionResponse sollte usage inkludieren."""
        response = ChatCompletionResponse(
            model="claude-sonnet-4",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content="Hello!"),
                    finish_reason="stop"
                )
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        )

        assert response.usage is not None
        assert response.usage.total_tokens == 15


# ============================================================================
# Test Class: ChatCompletionStreamResponse
# ============================================================================

class TestChatCompletionStreamResponse:
    """Tests für ChatCompletionStreamResponse model."""

    def test_creates_stream_response(self):
        """ChatCompletionStreamResponse sollte erstellt werden."""
        response = ChatCompletionStreamResponse(
            model="claude-sonnet-4",
            choices=[
                StreamChoice(
                    index=0,
                    delta={"role": "assistant", "content": "Hello"},
                    finish_reason=None
                )
            ]
        )

        assert response.object == "chat.completion.chunk"
        assert response.id.startswith("chatcmpl-")
        assert len(response.choices) == 1


# ============================================================================
# Test Class: Choice & StreamChoice
# ============================================================================

class TestChoiceModels:
    """Tests für Choice und StreamChoice models."""

    def test_choice_with_message(self):
        """Choice sollte mit message erstellt werden."""
        choice = Choice(
            index=0,
            message=Message(role="assistant", content="Hello"),
            finish_reason="stop"
        )

        assert choice.index == 0
        assert choice.message.content == "Hello"
        assert choice.finish_reason == "stop"

    def test_stream_choice_with_delta(self):
        """StreamChoice sollte mit delta erstellt werden."""
        choice = StreamChoice(
            index=0,
            delta={"content": "chunk"},
            finish_reason=None
        )

        assert choice.index == 0
        assert choice.delta["content"] == "chunk"
        assert choice.finish_reason is None


# ============================================================================
# Test Class: Usage
# ============================================================================

class TestUsage:
    """Tests für Usage model."""

    def test_creates_usage(self):
        """Usage sollte mit token counts erstellt werden."""
        usage = Usage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )

        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150


# ============================================================================
# Test Class: Error Models
# ============================================================================

class TestErrorModels:
    """Tests für ErrorDetail und ErrorResponse."""

    def test_creates_error_detail(self):
        """ErrorDetail sollte erstellt werden."""
        error = ErrorDetail(
            message="Invalid request",
            type="invalid_request_error",
            param="model",
            code="invalid_model"
        )

        assert error.message == "Invalid request"
        assert error.type == "invalid_request_error"
        assert error.param == "model"
        assert error.code == "invalid_model"

    def test_creates_error_response(self):
        """ErrorResponse sollte ErrorDetail wrappen."""
        response = ErrorResponse(
            error=ErrorDetail(
                message="Bad request",
                type="invalid_request_error"
            )
        )

        assert response.error.message == "Bad request"


# ============================================================================
# Test Class: Session Models
# ============================================================================

class TestSessionModels:
    """Tests für SessionInfo und SessionListResponse."""

    def test_creates_session_info(self):
        """SessionInfo sollte mit datetime fields erstellt werden."""
        now = datetime.utcnow()
        info = SessionInfo(
            session_id="session-123",
            created_at=now,
            last_accessed=now,
            message_count=5,
            expires_at=now
        )

        assert info.session_id == "session-123"
        assert info.message_count == 5

    def test_creates_session_list_response(self):
        """SessionListResponse sollte list of sessions wrappen."""
        now = datetime.utcnow()
        response = SessionListResponse(
            sessions=[
                SessionInfo(
                    session_id="session-1",
                    created_at=now,
                    last_accessed=now,
                    message_count=3,
                    expires_at=now
                ),
                SessionInfo(
                    session_id="session-2",
                    created_at=now,
                    last_accessed=now,
                    message_count=7,
                    expires_at=now
                )
            ],
            total=2
        )

        assert len(response.sessions) == 2
        assert response.total == 2


# ============================================================================
# Test Summary
# ============================================================================

"""
Test Summary für models.py:

✅ Test Coverage:
- ContentPart (2 Tests) - creation, validation
- Message (6 Tests) - string/array content, normalization, role validation
- ChatCompletionRequest (12 Tests) - minimal, defaults, validators, n>1, ranges, session_id, enable_tools, log warnings, to_claude_options
- ChatCompletionResponse (2 Tests) - defaults, usage
- ChatCompletionStreamResponse (1 Test) - stream response
- Choice & StreamChoice (2 Tests) - message/delta handling
- Usage (1 Test) - token counts
- ErrorDetail & ErrorResponse (2 Tests) - error wrapping
- SessionInfo & SessionListResponse (2 Tests) - session data

Total: 30 Tests

🎯 Test Strategy:
- Pydantic validation errors testen (ValidationError)
- Field validators (n>1, temperature/top_p ranges)
- Model validators (content normalization)
- Default values und auto-generation (id, created, object)
- Optional fields (usage, session_id, name)
- Log warnings für unsupported parameters
"""
