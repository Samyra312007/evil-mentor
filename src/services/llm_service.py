"""LLM Service for Evil Mentor.

Wraps the Google Gemini API (google.genai SDK) to provide content generation
for vulnerability analysis and feedback. Uses gemini-2.0-flash model with
retry logic and exponential backoff for resilience.
"""

import logging
import time

from google import genai

from src.config import Settings

logger = logging.getLogger(__name__)


class LLMService:
    """Google Gemini API wrapper for content generation.

    Uses the new ``google.genai`` SDK with ``gemini-2.0-flash`` model.
    Provides retry logic with exponential backoff (3 attempts) for API
    errors, and returns ``None`` for invalid/unparseable responses.
    """

    DEFAULT_MODEL = "gemini-2.0-flash"
    MAX_RETRIES = 3
    BASE_DELAY_SECONDS = 1.0  # first retry waits 1s, then 2s, then 4s

    def __init__(self, settings: Settings | None = None, model: str | None = None):
        self._settings = settings or Settings()
        self._model = model or self.DEFAULT_MODEL
        self._client = genai.Client(api_key=self._settings.GEMINI_API_KEY)

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str | None:
        """Call Gemini API and return the text response.

        Retries up to 3 times with exponential backoff on API errors.
        Returns ``None`` if the response is invalid or unparseable after
        all retries are exhausted.

        Args:
            prompt: The user prompt / content to send to the model.
            system_instruction: Optional system-level instruction for the
                model's behaviour.

        Returns:
            The generated text string, or ``None`` on failure.
        """
        config = None
        if system_instruction:
            config = genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
            )

        last_exception: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                )

                # Validate the response has usable text
                text = response.text
                if text is None or not text.strip():
                    logger.warning(
                        "Gemini returned empty/None text on attempt %d/%d",
                        attempt,
                        self.MAX_RETRIES,
                    )
                    last_exception = ValueError("Empty response from Gemini")
                    self._backoff(attempt)
                    continue

                return text

            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "Gemini API error on attempt %d/%d: %s",
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                )
                if attempt < self.MAX_RETRIES:
                    self._backoff(attempt)

        # All retries exhausted
        logger.warning(
            "Gemini API failed after %d attempts. Last error: %s",
            self.MAX_RETRIES,
            last_exception,
        )
        return None

    def _backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff: 1s, 2s, 4s, ..."""
        delay = self.BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        logger.debug("Backing off %.1fs before retry", delay)
        time.sleep(delay)
