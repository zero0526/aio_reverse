"""Domain-specific exceptions and error types."""


class AioReverseError(Exception):
    """Base error for all domain operations."""


class ArtifactNotFoundError(AioReverseError):
    """Raised when the target artifact cannot be located."""


class UnsupportedFormatError(AioReverseError):
    """Raised when an artifact format cannot be processed."""


class TimeoutError(AioReverseError):
    """Raised when an engine or operation exceeds its deadline."""


class EmulationFailureError(AioReverseError):
    """Raised when the execution sandbox fails to run target code."""


class SandboxResourceLimitError(AioReverseError):
    """Raised when sandboxed execution violates RAM/CPU budgets."""
