"""Harness-specific exception types."""


class HarnessError(RuntimeError):
    """Raised when a harness state file is invalid or cannot be updated."""
