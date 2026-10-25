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


class ToolkitError(AioReverseError):
    """Raised when the wre CLI fails or returns invalid output."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        returncode: int | None = None,
        stderr: str | None = None,
        stdout: str | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


class ToolkitNotFoundError(AioReverseError):
    """Raised when the wre binary cannot be located."""


class BrowserSessionError(AioReverseError):
    """Raised when the CDP session cannot be established or used."""


class AuthenticationRequiredError(AioReverseError):
    """Raised when the target page is not signed in."""


class FlowTimeoutError(AioReverseError):
    """Raised when a chat turn does not finish within its deadline."""


class ProbeUnavailableError(AioReverseError):
    """Raised when the requested probe is not installed in the page."""


class ActionScriptError(AioReverseError):
    """Raised when one action inside a script fails."""

    def __init__(
        self,
        script: str,
        step_index: int,
        action_type: str,
        message: str,
    ) -> None:
        super().__init__(
            f"action script {script!r} step {step_index} "
            f"({action_type}) failed: {message}"
        )
        self.script = script
        self.step_index = step_index
        self.action_type = action_type
        self.message = message
