"""Unit tests for LLMService."""

import logging
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.services.llm_service import LLMService


@pytest.fixture
def mock_settings():
    """Create mock settings with a fake API key."""
    settings = MagicMock()
    settings.GEMINI_API_KEY = "fake-api-key-for-testing"
    return settings


@pytest.fixture
def mock_client():
    """Create a mock genai.Client."""
    with patch("src.services.llm_service.genai.Client") as mock_cls:
        client_instance = MagicMock()
        mock_cls.return_value = client_instance
        yield client_instance


@pytest.fixture
def llm_service(mock_settings, mock_client):
    """Create an LLMService with mocked dependencies."""
    service = LLMService(settings=mock_settings)
    return service


class TestLLMServiceInit:
    """Tests for LLMService initialization."""

    def test_uses_default_model(self, mock_settings, mock_client):
        service = LLMService(settings=mock_settings)
        assert service._model == "gemini-2.0-flash"

    def test_accepts_custom_model(self, mock_settings, mock_client):
        service = LLMService(settings=mock_settings, model="gemini-1.5-pro")
        assert service._model == "gemini-1.5-pro"

    def test_creates_client_with_api_key(self, mock_settings):
        with patch("src.services.llm_service.genai.Client") as mock_cls:
            LLMService(settings=mock_settings)
            mock_cls.assert_called_once_with(api_key="fake-api-key-for-testing")


class TestGenerateContent:
    """Tests for generate_content method."""

    def test_returns_text_on_success(self, llm_service, mock_client):
        mock_response = MagicMock()
        mock_response.text = "Generated vulnerability code"
        mock_client.models.generate_content.return_value = mock_response

        result = llm_service.generate_content("Analyse this code")

        assert result == "Generated vulnerability code"

    def test_passes_prompt_to_api(self, llm_service, mock_client):
        mock_response = MagicMock()
        mock_response.text = "response"
        mock_client.models.generate_content.return_value = mock_response

        llm_service.generate_content("my prompt")

        call_kwargs = mock_client.models.generate_content.call_args
        assert call_kwargs.kwargs["contents"] == "my prompt"
        assert call_kwargs.kwargs["model"] == "gemini-2.0-flash"

    def test_passes_system_instruction(self, llm_service, mock_client):
        mock_response = MagicMock()
        mock_response.text = "response"
        mock_client.models.generate_content.return_value = mock_response

        llm_service.generate_content("prompt", system_instruction="be helpful")

        call_kwargs = mock_client.models.generate_content.call_args
        config = call_kwargs.kwargs["config"]
        assert config is not None

    def test_no_config_when_no_system_instruction(self, llm_service, mock_client):
        mock_response = MagicMock()
        mock_response.text = "response"
        mock_client.models.generate_content.return_value = mock_response

        llm_service.generate_content("prompt")

        call_kwargs = mock_client.models.generate_content.call_args
        assert call_kwargs.kwargs["config"] is None

    def test_returns_none_on_empty_response(self, llm_service, mock_client):
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client.models.generate_content.return_value = mock_response

        # Patch backoff to avoid real sleeps
        with patch.object(llm_service, "_backoff"):
            result = llm_service.generate_content("prompt")

        assert result is None

    def test_returns_none_on_none_text(self, llm_service, mock_client):
        mock_response = MagicMock()
        mock_response.text = None
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(llm_service, "_backoff"):
            result = llm_service.generate_content("prompt")

        assert result is None

    def test_retries_on_api_error(self, llm_service, mock_client):
        mock_response = MagicMock()
        mock_response.text = "success after retry"
        mock_client.models.generate_content.side_effect = [
            RuntimeError("API error"),
            mock_response,
        ]

        with patch.object(llm_service, "_backoff"):
            result = llm_service.generate_content("prompt")

        assert result == "success after retry"
        assert mock_client.models.generate_content.call_count == 2

    def test_returns_none_after_max_retries(self, llm_service, mock_client):
        mock_client.models.generate_content.side_effect = RuntimeError("API down")

        with patch.object(llm_service, "_backoff"):
            result = llm_service.generate_content("prompt")

        assert result is None
        assert mock_client.models.generate_content.call_count == 3

    def test_logs_warning_on_failure(self, llm_service, mock_client, caplog):
        mock_client.models.generate_content.side_effect = RuntimeError("boom")

        with patch.object(llm_service, "_backoff"):
            with caplog.at_level(logging.WARNING):
                llm_service.generate_content("prompt")

        assert any("Gemini API" in msg for msg in caplog.messages)

    def test_exponential_backoff_called(self, llm_service, mock_client):
        mock_client.models.generate_content.side_effect = RuntimeError("fail")

        with patch.object(llm_service, "_backoff") as mock_backoff:
            llm_service.generate_content("prompt")

        # Should backoff after attempt 1 and 2 (not after the last attempt)
        assert mock_backoff.call_count == 2
        mock_backoff.assert_any_call(1)
        mock_backoff.assert_any_call(2)


class TestBackoff:
    """Tests for the _backoff method."""

    def test_backoff_delay_increases(self, llm_service):
        with patch("src.services.llm_service.time.sleep") as mock_sleep:
            llm_service._backoff(1)
            mock_sleep.assert_called_with(1.0)

            llm_service._backoff(2)
            mock_sleep.assert_called_with(2.0)

            llm_service._backoff(3)
            mock_sleep.assert_called_with(4.0)
