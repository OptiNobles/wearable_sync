"""Entrypoint for the scheduled sync job.

Run with: uv run training-hub-sync  (or: python -m training_hub.jobs.daily_sync)
Exit code 0 means every (source, data type) pair synced; 1 means something failed.
"""

import logging
import sys
from contextlib import ExitStack
from datetime import date, timedelta

from training_hub.config import Settings
from training_hub.services.sync import sync
from training_hub.sinks.local import LocalFileSink
from training_hub.sources.registry import build_sources

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
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
    sink = LocalFileSink(settings.local_sink_root)

    logger.info("Sync started: sources=%s since=%s", settings.enabled_sources, since)
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
