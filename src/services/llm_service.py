"""LLM Service for Evil Mentor.

Wraps the Groq API to provide content generation for vulnerability
analysis and feedback. Uses llama-3.3-70b-versatile model with retry
logic and exponential backoff for resilience.
"""

import logging
import time

from groq import Groq

from src.config import Settings

logger = logging.getLogger(__name__)


class LLMService:
    """Groq API wrapper for content generation.

    Uses ``llama-3.3-70b-versatile`` model via Groq's fast inference.
    Provides retry logic with exponential backoff (3 attempts) for API
    errors, and returns ``None`` for invalid/unparseable responses.
    """

    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    MAX_RETRIES = 3
    BASE_DELAY_SECONDS = 1.0

    def __init__(self, settings: Settings | None = None, model: str | None = None):
        self._settings = settings or Settings()
        self._model = model or self.DEFAULT_MODEL
        self._client = Groq(api_key=self._settings.GROQ_API_KEY)

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str | None:
        """Call Groq API and return the text response.

        Retries up to 3 times with exponential backoff on API errors.
        Returns ``None`` if the response is invalid or unparseable after
        all retries are exhausted.

        Args:
            prompt: The user prompt / content to send to the model.
            system_instruction: Optional system-level instruction.

        Returns:
            The generated text string, or ``None`` on failure.
        """
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        last_exception: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4096,
                )

                text = response.choices[0].message.content
                if text is None or not text.strip():
                    logger.warning(
                        "Groq returned empty/None text on attempt %d/%d",
                        attempt,
                        self.MAX_RETRIES,
                    )
                    last_exception = ValueError("Empty response from Groq")
                    self._backoff(attempt)
                    continue

                return text

            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "Groq API error on attempt %d/%d: %s",
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                )
                if attempt < self.MAX_RETRIES:
                    self._backoff(attempt)

        logger.warning(
            "Groq API failed after %d attempts. Last error: %s",
            self.MAX_RETRIES,
            last_exception,
        )
        return None

    def _backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff: 1s, 2s, 4s, ..."""
        delay = self.BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        logger.debug("Backing off %.1fs before retry", delay)
        time.sleep(delay)
