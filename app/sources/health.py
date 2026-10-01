"""Manual live smoke test for configured EIS RSS source."""
from __future__ import annotations

import asyncio
import sys

from app.monitoring.config import MonitoringConfigurationError, load_monitoring_settings
from app.sources.eis_rss import EisRssSource, SourceError


async def _run() -> int:
    try:
        settings = load_monitoring_settings()
    except MonitoringConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    if not settings.eis_rss_urls:
        print("EIS_RSS_URLS is empty. Add at least one RSS URL to .env.", file=sys.stderr)
        return 2
    source = EisRssSource(
        urls=settings.eis_rss_urls,
        timeout=settings.request_timeout,
        ca_bundle_file=settings.ca_bundle_file,
    )
    try:
        notices = await source.fetch(min(settings.max_items, 5))
    except SourceError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"EIS RSS: OK | feeds={len(settings.eis_rss_urls)} | notices={len(notices)}")
    if notices:
        print(f"Sample: {notices[0].title[:160]}")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
