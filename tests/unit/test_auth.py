"""
Unit Tests für Authentication Module (auth.py)

Testet:
- Claude CLI OAuth Authentication (KRITISCH)
- Optional API_KEY FastAPI-Endpunkt-Schutz
- ANTHROPIC_API_KEY Warning
"""

import os
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

# Import der zu testenden Module
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.auth import (
    ClaudeCodeAuthManager,
    verify_api_key,
    validate_claude_code_auth,
    get_claude_code_auth_info
)


class TestClaudeCodeAuthManager:
    """Tests für ClaudeCodeAuthManager Klasse"""

    def test_detect_auth_method_claude_cli(self):
        """Auth method sollte 'claude_cli' sein (OAuth)"""
        # Given: Keine Bedrock/Vertex env vars
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)

        # When: ClaudeCodeAuthManager initialisiert
        auth_manager = ClaudeCodeAuthManager()

        # Then: Auth method ist 'claude_cli'
        assert auth_manager.auth_method == "claude_cli"

    def test_detect_auth_method_bedrock(self):
        """Mit CLAUDE_CODE_USE_BEDROCK=1 sollte bedrock erkannt werden"""
        # Given: Bedrock env var gesetzt
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)

        # When
        auth_manager = ClaudeCodeAuthManager()

        # Then
        assert auth_manager.auth_method == "bedrock"

        # Cleanup
        del os.environ["CLAUDE_CODE_USE_BEDROCK"]

    def test_detect_auth_method_vertex(self):
        """Mit CLAUDE_CODE_USE_VERTEX=1 sollte vertex erkannt werden"""
        # Given: Vertex env var gesetzt
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ["CLAUDE_CODE_USE_VERTEX"] = "1"

        # When
        auth_manager = ClaudeCodeAuthManager()

        # Then
        assert auth_manager.auth_method == "vertex"

        # Cleanup
        del os.environ["CLAUDE_CODE_USE_VERTEX"]

    def test_anthropic_api_key_warning(self, caplog):
        """ANTHROPIC_API_KEY sollte Warning triggern und ignoriert werden"""
        # Given: ANTHROPIC_API_KEY in environment
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-123456"
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)

        # When: ClaudeCodeAuthManager initialisiert
        auth_manager = ClaudeCodeAuthManager()

        # Then: Warning geloggt
        assert "ANTHROPIC_API_KEY detected" in caplog.text
        assert "will be IGNORED" in caplog.text

        # Auth method ist trotzdem claude_cli
        assert auth_manager.auth_method == "claude_cli"

        # Cleanup
        del os.environ["ANTHROPIC_API_KEY"]

    def test_validate_claude_cli_auth(self):
        """Claude CLI OAuth Validation sollte immer True sein"""
        # Given: Auth manager mit claude_cli method
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)
        auth_manager = ClaudeCodeAuthManager()

        # When: Validation durchgeführt
        status = auth_manager._validate_claude_cli_auth()

        # Then: Immer valid
        assert status["valid"] is True
        assert len(status["errors"]) == 0
        assert status["config"]["method"] == "Claude Code CLI authentication"

    def test_validate_bedrock_auth_missing_credentials(self):
        """Bedrock ohne AWS credentials sollte Fehler geben"""
        # Given: Bedrock aktiviert, aber keine AWS credentials
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
        os.environ.pop("AWS_REGION", None)

        # When
        auth_manager = ClaudeCodeAuthManager()

        # Then: Validation fehlgeschlagen
        assert auth_manager.auth_status["valid"] is False
        assert len(auth_manager.auth_status["errors"]) > 0

        # Cleanup
        del os.environ["CLAUDE_CODE_USE_BEDROCK"]

    def test_validate_vertex_auth_missing_credentials(self):
        """Vertex ohne GCP credentials sollte Fehler geben"""
        # Given: Vertex aktiviert, aber keine GCP credentials
        os.environ["CLAUDE_CODE_USE_VERTEX"] = "1"
        os.environ.pop("ANTHROPIC_VERTEX_PROJECT_ID", None)
        os.environ.pop("CLOUD_ML_REGION", None)

        # When
        auth_manager = ClaudeCodeAuthManager()

        # Then: Validation fehlgeschlagen
        assert auth_manager.auth_status["valid"] is False
        assert len(auth_manager.auth_status["errors"]) > 0

        # Cleanup
        del os.environ["CLAUDE_CODE_USE_VERTEX"]

    def test_get_claude_code_env_vars_empty_for_cli(self):
        """Für Claude CLI OAuth sollten keine env vars nötig sein"""
        # Given: claude_cli auth method
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)
        auth_manager = ClaudeCodeAuthManager()

        # When: Get env vars
        env_vars = auth_manager.get_claude_code_env_vars()

        # Then: Empty dict (keine env vars nötig)
        assert env_vars == {}

    def test_get_claude_code_env_vars_bedrock(self):
        """Für Bedrock sollten AWS env vars zurückgegeben werden"""
        # Given: Bedrock mit AWS credentials
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        os.environ["AWS_ACCESS_KEY_ID"] = "test-key"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret"
        os.environ["AWS_REGION"] = "us-east-1"

        # When
        auth_manager = ClaudeCodeAuthManager()
        env_vars = auth_manager.get_claude_code_env_vars()

        # Then: AWS env vars vorhanden
        assert "CLAUDE_CODE_USE_BEDROCK" in env_vars
        assert "AWS_ACCESS_KEY_ID" in env_vars
        assert "AWS_SECRET_ACCESS_KEY" in env_vars
        assert "AWS_REGION" in env_vars

        # Cleanup
        for key in ["CLAUDE_CODE_USE_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]:
            del os.environ[key]

    def test_get_api_key_from_env(self):
        """get_api_key sollte API_KEY aus env var lesen"""
        # Given: API_KEY env var gesetzt
        os.environ["API_KEY"] = "test-api-key-123"
        auth_manager = ClaudeCodeAuthManager()

        # When
        api_key = auth_manager.get_api_key()

        # Then
        assert api_key == "test-api-key-123"

        # Cleanup
        del os.environ["API_KEY"]

    def test_get_api_key_none_when_not_set(self):
        """get_api_key sollte None zurückgeben wenn nicht gesetzt"""
        # Given: Kein API_KEY env var
        os.environ.pop("API_KEY", None)
        auth_manager = ClaudeCodeAuthManager()

        # When
        api_key = auth_manager.get_api_key()

        # Then
        assert api_key is None


class TestVerifyApiKey:
    """Tests für verify_api_key Funktion (Optional FastAPI-Endpunkt-Schutz)"""

    @pytest.mark.asyncio
    async def test_no_api_key_configured_allows_all(self):
        """Ohne API_KEY env var sollten alle Requests durchkommen"""
        # Given: Kein API_KEY gesetzt
        os.environ.pop("API_KEY", None)

        # Mock Request ohne Authorization header
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        # When: verify_api_key aufgerufen ohne credentials
        result = await verify_api_key(mock_request, credentials=None)

        # Then: Request erlaubt
        assert result is True

    @pytest.mark.asyncio
    async def test_valid_api_key_passes(self):
        """Mit API_KEY und gültigem Bearer Token sollte Request durchkommen"""
        # Given: API_KEY env var gesetzt
        os.environ["API_KEY"] = "test-key-123"

        # Mock credentials
        mock_creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test-key-123"
        )

        mock_request = Mock(spec=Request)

        # When
        result = await verify_api_key(mock_request, credentials=mock_creds)

        # Then
        assert result is True

        # Cleanup
        del os.environ["API_KEY"]

    @pytest.mark.asyncio
    async def test_invalid_api_key_raises_401(self):
        """Mit API_KEY und falschem Bearer Token sollte 401 kommen"""
        # Mock: Simuliere dass API_KEY gesetzt ist
        with patch('auth.auth_manager.get_api_key', return_value="test-key-123"):
            # Mock credentials mit falschem key
            mock_creds = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="wrong-key"
            )

            mock_request = Mock(spec=Request)

            # When/Then: HTTPException 401
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(mock_request, credentials=mock_creds)

            assert exc_info.value.status_code == 401
            assert "Invalid API key" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_401(self):
        """Mit API_KEY aber ohne Authorization header sollte 401 kommen"""
        # Mock: Simuliere dass API_KEY gesetzt ist
        with patch('auth.auth_manager.get_api_key', return_value="test-key-123"):
            # Mock Request ohne credentials
            mock_request = Mock(spec=Request)
            mock_request.headers = {}

            # Mock security callable als async function die None zurückgibt
            async def mock_security_func(request):
                return None

            with patch('auth.security', side_effect=mock_security_func):
                # When/Then: HTTPException 401
                with pytest.raises(HTTPException) as exc_info:
                    await verify_api_key(mock_request, credentials=None)

                assert exc_info.value.status_code == 401
                assert "Missing API key" in str(exc_info.value.detail)


class TestValidateClaudeCodeAuth:
    """Tests für validate_claude_code_auth Funktion"""

    def test_validate_claude_code_auth_success(self):
        """validate_claude_code_auth sollte für claude_cli True zurückgeben"""
        # Given: Claude CLI OAuth konfiguriert
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)

        # When
        is_valid, status = validate_claude_code_auth()

        # Then
        assert is_valid is True
        assert status["valid"] is True
        assert status["method"] == "claude_cli"
        assert len(status["errors"]) == 0

    def test_validate_claude_code_auth_bedrock_missing_creds(self):
        """validate_claude_code_auth sollte für Bedrock ohne Creds False geben"""
        # Given: Bedrock ohne AWS credentials
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_DEFAULT_REGION", None)

        # Re-initialisiere auth_manager mit neuen env vars
        from auth import ClaudeCodeAuthManager
        import auth
        auth.auth_manager = ClaudeCodeAuthManager()

        # When
        is_valid, status = validate_claude_code_auth()

        # Then
        assert is_valid is False
        assert status["valid"] is False
        assert len(status["errors"]) > 0

        # Cleanup
        del os.environ["CLAUDE_CODE_USE_BEDROCK"]


class TestGetClaudeCodeAuthInfo:
    """Tests für get_claude_code_auth_info Funktion"""

    def test_get_auth_info_returns_dict(self):
        """get_claude_code_auth_info sollte Auth-Info zurückgeben"""
        # Given: Claude CLI OAuth (re-initialisiere auth_manager)
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)

        # Re-initialisiere auth_manager um sicherzustellen dass claude_cli aktiv ist
        from auth import ClaudeCodeAuthManager
        import auth
        auth.auth_manager = ClaudeCodeAuthManager()

        # When
        info = get_claude_code_auth_info()

        # Then
        assert "method" in info
        assert "status" in info
        assert "environment_variables" in info
        assert info["method"] == "claude_cli"
        assert isinstance(info["environment_variables"], list)


# Fixtures
@pytest.fixture(autouse=True)
def cleanup_env():
    """Cleanup environment variables nach jedem Test"""
    yield
    # Cleanup nach Test
    for key in ["API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION",
                "ANTHROPIC_VERTEX_PROJECT_ID", "CLOUD_ML_REGION"]:
        os.environ.pop(key, None)
