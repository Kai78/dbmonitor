from dbmonitor_sdk.errors import (
    ErrorCategory,
    PermanentPluginError,
    SchemaValidationError,
    TransientPluginError,
)
from dbmonitor_sdk.groups import STANDARD_COLLECTOR_GROUPS, validate_collector_groups
from dbmonitor_sdk.models.profile import PollingPool, PollingProfile, RetryPolicy
from dbmonitor_sdk.models.results import CollectorResult, PollResult, ResultEnvelope
from dbmonitor_sdk.models.server import DiscoveredServer, DiscoveryContext
from dbmonitor_sdk.models.target import DatabaseTarget

__version__ = "1.2.0"

__all__ = [
    "CollectorResult",
    "DatabaseTarget",
    "DiscoveredServer",
    "DiscoveryContext",
    "ErrorCategory",
    "PermanentPluginError",
    "PollResult",
    "PollingPool",
    "PollingProfile",
    "ResultEnvelope",
    "RetryPolicy",
    "STANDARD_COLLECTOR_GROUPS",
    "SchemaValidationError",
    "TransientPluginError",
    "__version__",
    "validate_collector_groups",
]
