"""
Custom exceptions for AutoDev system.
"""


class AutoDevError(Exception):
    """Base exception for all AutoDev errors."""
    pass


class ConfigurationError(AutoDevError):
    """Raised when there's a configuration problem."""
    pass


class ProjectNotFoundError(AutoDevError):
    """Raised when the project directory doesn't exist."""
    pass


class FeatureListError(AutoDevError):
    """Raised when there's a problem with the feature list."""
    pass


class SessionError(AutoDevError):
    """Raised when there's a session-related error."""
    pass


class AgentError(AutoDevError):
    """Raised when an agent encounters an error."""
    pass


class GitError(AutoDevError):
    """Raised when a git operation fails."""
    pass


class TestError(AutoDevError):
    """Raised when a test fails unexpectedly."""
    pass


class MaxIterationsExceeded(AutoDevError):
    """Raised when the maximum number of iterations is exceeded."""
    pass


class EnvironmentNotHealthy(AutoDevError):
    """Raised when the development environment is not in a healthy state."""
    pass


class LLMError(AutoDevError):
    """Raised when there's an error with the LLM API."""
    pass


class TimeoutError(AutoDevError):
    """Raised when an operation times out."""
    pass
