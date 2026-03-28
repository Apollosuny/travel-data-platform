class ProviderError(Exception):
  """Base error for provider-related failures."""

class ProviderFetchError(ProviderError):
    """Raised when fetching raw provider data fails."""


class ProviderParseError(ProviderError):
    """Raised when parsing provider data fails."""