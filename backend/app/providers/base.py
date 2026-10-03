"""Shared bits for provider clients."""


class ProviderError(Exception):
    """A provider call failed — message is shown verbatim in the admin panel."""


class ProviderNotConfigured(ProviderError):
    pass


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
