"""Training hours enforcement utilities.

Provides functions to check whether the current time falls within
the configured training window and to generate user-friendly messages.
"""


def is_within_training_hours(current_hour: int, start_hour: int, end_hour: int) -> bool:
    """Check if the current hour is within the allowed training window.

    The training window is defined as [start_hour, end_hour), meaning
    start_hour is inclusive and end_hour is exclusive.

    Args:
        current_hour: The current hour of the day (0–23).
        start_hour: The start of the training window (0–23), inclusive.
        end_hour: The end of the training window (0–23), exclusive.

    Returns:
        True if start_hour <= current_hour < end_hour, False otherwise.
    """
    return start_hour <= current_hour < end_hour


def get_training_window_message(start_hour: int, end_hour: int) -> str:
    """Return a user-friendly message describing the allowed training window.

    Args:
        start_hour: The start of the training window (0–23).
        end_hour: The end of the training window (0–23).

    Returns:
        A human-readable string indicating when training is available.
    """
    start_formatted = _format_hour(start_hour)
    end_formatted = _format_hour(end_hour)
    return (
        f"Training is only available between {start_formatted} and "
        f"{end_formatted}. Please try again during the training window."
    )


def _format_hour(hour: int) -> str:
    """Format an hour (0–23) as a 12-hour time string with AM/PM.

    Args:
        hour: Hour of the day (0–23).

    Returns:
        Formatted time string, e.g. "9:00 AM", "6:00 PM", "12:00 PM".
    """
    if hour == 0:
        return "12:00 AM"
    elif hour < 12:
        return f"{hour}:00 AM"
    elif hour == 12:
        return "12:00 PM"
    else:
        return f"{hour - 12}:00 PM"
