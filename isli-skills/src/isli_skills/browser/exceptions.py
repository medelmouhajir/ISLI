"""Browser automation exceptions."""


class BrowserError(Exception):
    """Base exception for browser automation errors."""

    pass


class BrowserRefError(BrowserError):
    """Raised when a ref ID is unknown or stale."""

    pass


class BrowserSessionError(BrowserError):
    """Raised when a browser session cannot be created or closed."""

    pass
