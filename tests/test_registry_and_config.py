from contextlib import ExitStack

import pytest
from pydantic import ValidationError

from training_hub.config import Settings
from training_hub.sources.polar.source import PolarSource
from training_hub.sources.registry import build_sources


def make_settings(**overrides: object) -> Settings:
    # _env_file=None: tests must not depend on the developer's local .env
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENABLED_SOURCES", "LOOKBACK_DAYS", "POLAR_ACCESS_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_enabled_sources_are_parsed_from_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLED_SOURCES", " polar , garmin ,")

    assert make_settings().enabled_sources == ["polar", "garmin"]


def test_duplicate_sources_are_removed_keeping_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLED_SOURCES", "polar,garmin,polar")

    assert make_settings().enabled_sources == ["polar", "garmin"]


def test_empty_enabled_sources_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLED_SOURCES", "")

    assert make_settings().enabled_sources == ["polar"]


@pytest.mark.parametrize("value", [",", " , "])
def test_enabled_sources_without_any_name_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ENABLED_SOURCES", value)

    with pytest.raises(ValidationError):
        make_settings()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_lookback_days_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("LOOKBACK_DAYS", value)

    with pytest.raises(ValidationError):
        make_settings()


def test_empty_token_env_is_treated_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLAR_ACCESS_TOKEN", "")

    assert make_settings().polar_access_token is None


def test_polar_source_is_built_when_token_is_set() -> None:
    settings = make_settings(polar_access_token="test-token")

    with ExitStack() as stack:
        sources = build_sources(["polar"], settings, stack)

    assert [type(s) for s in sources] == [PolarSource]


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_or_blank_polar_token_fails_with_clear_message(token: str | None) -> None:
    settings = make_settings(polar_access_token=token)

    with ExitStack() as stack, pytest.raises(ValueError, match="POLAR_ACCESS_TOKEN"):
        build_sources(["polar"], settings, stack)


def test_unknown_source_is_rejected() -> None:
    settings = make_settings(polar_access_token="test-token")

    with ExitStack() as stack, pytest.raises(ValueError, match="Unknown sources: \\['garmin'\\]"):
        build_sources(["polar", "garmin"], settings, stack)
