"""Entrypoint for the scheduled sync job.

Run with: uv run wearable-sync  (or: python -m wearable_sync.jobs.daily_sync)
Exit code 0 means every (source, data type) pair synced; 1 means something failed.
"""

import logging
import sys
from contextlib import ExitStack
from datetime import date, timedelta

import truststore

from wearable_sync.config import Settings
from wearable_sync.services.sync import sync
from wearable_sync.sinks.factory import build_sink
from wearable_sync.sources.registry import build_sources

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # The SDK logs an INFO line per uploaded file; keep its warnings and errors only.
    logging.getLogger("databricks.sdk").setLevel(logging.WARNING)
    # Use the OS certificate store for every library (the Databricks SDK uses
    # requests/certifi): needed behind antivirus HTTPS inspection, harmless elsewhere.
    truststore.inject_into_ssl()
    try:
        return _run()
    except Exception:
        # Configuration and setup errors (invalid settings, unknown source,
        # missing token) abort the whole run; per-pair errors are handled in sync().
        logger.exception("Sync aborted")
        return 1


def _run() -> int:
    settings = Settings()
    since = date.today() - timedelta(days=settings.lookback_days)
    sink = build_sink(settings)

    logger.info(
        "Sync started: sources=%s sink=%s since=%s", settings.enabled_sources, settings.sink, since
    )
    with ExitStack() as stack:
        sources = build_sources(settings.enabled_sources, settings, stack)
        report = sync(sources, sink, since)

    if report.succeeded:
        logger.info("Sync finished: new_records=%d", report.total_new_records)
        return 0
    # Details with tracebacks were already logged by sync(); this is the summary.
    failed_pairs = [f"{f.source}/{f.data_type}" for f in report.failures]
    logger.warning(
        "Sync finished with failures: new_records=%d failed=%s",
        report.total_new_records,
        failed_pairs,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
