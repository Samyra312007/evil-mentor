"""Evil Mentor configuration module.

Reads all settings from environment variables using Pydantic Settings.
No secrets are hardcoded — everything comes from the environment.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    GROQ_API_KEY: str = Field(default="", description="Groq API key")
    GROQ_API_KEY: str = Field(default="", description="Groq API key (fallback LLM)")

    # ArmorIQ
    ARMORIQ_API_KEY: str = Field(default="", description="ArmorIQ API key")
    ARMORIQ_USER_ID: str = Field(default="", description="ArmorIQ user ID")
    ARMORIQ_AGENT_ID: str = Field(default="", description="ArmorIQ agent ID")

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///evil_mentor.db",
        description="Database connection URL",
    )

    # Training window
    TRAINING_START_HOUR: int = Field(
        default=9,
        description="Start of allowed training window (0-23)",
    )
    TRAINING_END_HOUR: int = Field(
        default=18,
        description="End of allowed training window (0-23)",
    )

    # Rate limiting
    MAX_INJECTIONS_PER_DAY: int = Field(
        default=10,
        description="Maximum training sessions per user per day",
    )

    # Branch protection
    BLOCKED_BRANCHES: str = Field(
        default="main,master,production",
        description="Comma-separated list of protected branch names",
    )

    # Demo mode — skip ArmorIQ policy gate
    SKIP_ARMORIQ: bool = Field(
        default=False,
        description="Skip ArmorIQ policy gate for demo/testing",
    )

    @property
    def blocked_branch_set(self) -> set[str]:
        """Return blocked branches as a lowercase set."""
        return {b.strip().lower() for b in self.BLOCKED_BRANCHES.split(",")}

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
