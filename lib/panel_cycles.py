"""Helpers for automatic panel selection."""


def rainfall_takeover_button(button_list):
    """Return the Rainfall cycle to switch, unless Rainfall is primary."""

    if any(button[5][0] == 'Rainfall' for button in button_list):
        return None
    return next((button for button in button_list
                 if 'Rainfall' in button[5]), None)
