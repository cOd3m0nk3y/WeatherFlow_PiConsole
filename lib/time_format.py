"""Shared display-time formatting helpers."""


def format_clock(value, time_format):
    """Format a datetime using the configured 12- or 24-hour display."""
    if time_format == '12 hr':
        return value.strftime('%I:%M %p').lstrip('0')
    return value.strftime('%H:%M')
