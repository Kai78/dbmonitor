from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    AUTHENTICATION_FAILED = "authentication_failed"
    TARGET_UNREACHABLE = "target_unreachable"
    QUERY_TIMEOUT = "query_timeout"
    PERMISSION_DENIED = "permission_denied"
    INVALID_CONFIGURATION = "invalid_configuration"
    UNKNOWN_PLUGIN = "unknown_plugin"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    SCHEMA_NOT_READY = "schema_not_ready"
    INTERNAL_ERROR = "internal_error"


class PluginError(Exception):
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.INTERNAL_ERROR) -> None:
        super().__init__(message)
        self.category = category


class TransientPluginError(PluginError):
    """Retryable within task deadline for low-frequency pools."""


class PermanentPluginError(PluginError):
    """Fail-fast error; never retried."""


class SchemaValidationError(Exception):
    """Raised when plugin schema manifest or output violates the schema contract."""
