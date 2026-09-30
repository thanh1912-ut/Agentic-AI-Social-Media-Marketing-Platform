"""Provider-neutral failures shared by agent handlers and model adapters."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Safe-to-report provider failure; never includes credentials or raw bodies."""

    retryable = False
    http_status: int | None = None

    def __init__(self, message: str, *, retryable: bool | None = None, repair_attempts: int = 0):
        super().__init__(message)
        if retryable is not None:
            self.retryable = retryable
        self.repair_attempts = repair_attempts


class ProviderConfigurationError(ProviderError):
    """Required server-side provider configuration is missing or invalid."""


class ProviderTimeoutError(ProviderError):
    """The provider request exceeded its configured timeout."""

    retryable = True


class ProviderAuthenticationError(ProviderError):
    """Provider credentials were rejected."""


class ProviderRateLimitError(ProviderError):
    """The provider rate limit was reached."""

    retryable = True


class ProviderModelNotFoundError(ProviderError):
    """The configured model ID is unavailable to this provider account."""


class ProviderOutputError(ProviderError):
    """The provider returned empty, incomplete, invalid, or ungrounded output."""

    repairable = True


class ProviderContextLimitError(ProviderError):
    """The serialized prompt exceeds this adapter's configured input bound."""


class ProviderRequestError(ProviderError):
    """The provider rejected or failed a request for another reason."""


def safe_provider_error_code(error: Exception) -> str:
    """A bounded diagnostic code without headers, URLs, bodies or source text."""
    if isinstance(error, ProviderError):
        status = error.http_status
        if type(status) is int and 400 <= status <= 599:
            return f"provider_http_{status}"
        if isinstance(error, ProviderOutputError):
            return "provider_output_invalid"
        if isinstance(error, ProviderTimeoutError):
            return "provider_timeout"
    return "provider_call_outcome_unknown"
