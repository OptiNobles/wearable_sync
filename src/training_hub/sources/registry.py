"""Maps source names (as used in ENABLED_SOURCES) to source factories."""

from collections.abc import Callable, Iterable
from contextlib import ExitStack

from training_hub.config import Settings
from training_hub.core.interfaces import Source
from training_hub.sources.polar.client import PolarClient
from training_hub.sources.polar.source import PolarSource

# A factory registers every resource it opens (e.g. HTTP clients) on the stack,
# so the caller can close all of them at once.
SourceFactory = Callable[[Settings, ExitStack], Source]


def _create_polar(settings: Settings, stack: ExitStack) -> Source:
    token = settings.polar_access_token
    if token is None or not token.get_secret_value().strip():
        raise ValueError("POLAR_ACCESS_TOKEN is required when source 'polar' is enabled")
    client = stack.enter_context(
        PolarClient(settings.polar_access_token, base_url=settings.polar_base_url)
    )
    return PolarSource(client)


SOURCE_FACTORIES: dict[str, SourceFactory] = {
    "polar": _create_polar,
}


def build_sources(names: Iterable[str], settings: Settings, stack: ExitStack) -> list[Source]:
    names = list(names)
    unknown = sorted(set(names) - SOURCE_FACTORIES.keys())
    if unknown:
        raise ValueError(f"Unknown sources: {unknown}. Available: {sorted(SOURCE_FACTORIES)}")
    return [SOURCE_FACTORIES[name](settings, stack) for name in names]
