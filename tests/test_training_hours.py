"""Unit tests for training hours enforcement."""

import pytest

from src.utils.training_hours import (
    get_training_window_message,
    is_within_training_hours,
)


class TestIsWithinTrainingHours:
    """Tests for is_within_training_hours."""

    def test_within_default_window(self):
        """Hour 12 is within the default 9–18 window."""
        assert is_within_training_hours(12, 9, 18) is True

    def test_at_start_boundary(self):
        """Start hour is inclusive."""
        assert is_within_training_hours(9, 9, 18) is True

    def test_at_end_boundary(self):
        """End hour is exclusive."""
        assert is_within_training_hours(18, 9, 18) is False

    def test_before_window(self):
        assert is_within_training_hours(7, 9, 18) is False

    def test_after_window(self):
        assert is_within_training_hours(20, 9, 18) is False

    def test_midnight(self):
        assert is_within_training_hours(0, 9, 18) is False

    def test_hour_23(self):
        assert is_within_training_hours(23, 9, 18) is False

    def test_narrow_window(self):
        """Single-hour window: only hour 10 is allowed."""
        assert is_within_training_hours(10, 10, 11) is True
        assert is_within_training_hours(9, 10, 11) is False
        assert is_within_training_hours(11, 10, 11) is False

    def test_full_day_window(self):
        """0–24 window allows every hour."""
        for h in range(24):
            assert is_within_training_hours(h, 0, 24) is True


class TestGetTrainingWindowMessage:
    """Tests for get_training_window_message."""

    def test_default_window_message(self):
        msg = get_training_window_message(9, 18)
        assert "9:00 AM" in msg
        assert "6:00 PM" in msg
        assert "training" in msg.lower()

    def test_midnight_start(self):
        msg = get_training_window_message(0, 8)
        assert "12:00 AM" in msg
        assert "8:00 AM" in msg

    def test_noon_boundary(self):
        msg = get_training_window_message(12, 17)
        assert "12:00 PM" in msg
        assert "5:00 PM" in msg

    def test_message_contains_guidance(self):
        msg = get_training_window_message(9, 18)
        assert "try again" in msg.lower() or "please" in msg.lower()
