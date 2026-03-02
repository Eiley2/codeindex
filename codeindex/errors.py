from __future__ import annotations


class CodeIndexError(Exception):
    """Base exception for domain errors."""


class ConfigurationError(CodeIndexError):
    """Raised for invalid or missing configuration."""


class ValidationError(CodeIndexError):
    """Raised for invalid user input."""


class NotFoundError(CodeIndexError):
    """Raised when an index or resource does not exist."""


class DatabaseError(CodeIndexError):
    """Raised for database interaction failures."""
