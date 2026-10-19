"""Configuration for Phase 9 tender monitoring."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from app.network import configure_http_environment

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class MonitoringConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class MonitoringSettings:
    enabled: bool
    interval_seconds: int
    max_items: int
    max_notifications_per_cycle: int
    request_timeout: float
    eis_rss_urls: tuple[str, ...]
    ca_bundle_file: Path | None
    profile_feeds_enabled: bool = True
    profile_feed_limit: int = 5

    eis_223_enabled: bool = False
    eis_223_rss_urls: tuple[str, ...] = ()
    eis_223_profile_feeds_enabled: bool = False
    b2b_center_enabled: bool = False
    tektorg_public_enabled: bool = False
    mikroton_tender_enabled: bool = False
    gpb_etp_public_enabled: bool = False
    lenobl_small_public_enabled: bool = False
    nmck_native_public_enabled: bool = False
    stan_commercial_public_enabled: bool = False
    south_ural_public_enabled: bool = False
    ru_dagestan_public_list_enabled: bool = False
    ru_samara_public_list_enabled: bool = False
    kavkaz_rf_firstparty_enabled: bool = False
    ru_background_catalog_enabled: bool = False
    eis_direct_enabled: bool = False
    eis_system_trust_enabled: bool = False
    eis_44_html_enabled: bool = False
    cis_md_elicitatie_enabled: bool = False
    cis_az_azeristilik_enabled: bool = False
    cis_az_adif_small_enabled: bool = False

    @property
    def eis_223_configured(self) -> bool:
        return self.eis_223_enabled and (bool(self.eis_223_rss_urls) or self.eis_223_profile_feeds_enabled)

    @property
    def source_configured(self) -> bool:
        return bool(self.eis_rss_urls) or self.profile_feeds_enabled


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise MonitoringConfigurationError(f"{name} должен быть true/false.")


def _urls(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for raw in value.split(";"):
        url = raw.strip()
        if not url:
            continue
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise MonitoringConfigurationError("EIS_RSS_URLS должен содержать HTTPS URL, разделённые ';'.")
        result.append(url)
    return tuple(dict.fromkeys(result))


def load_monitoring_settings(env_file: Path = ENV_FILE) -> MonitoringSettings:
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    try:
        interval = int(os.environ.get("MONITOR_INTERVAL_SECONDS", "600") or "600")
        max_items = int(os.environ.get("MONITOR_MAX_ITEMS", "20") or "20")
        max_notifications = int(os.environ.get("MONITOR_MAX_NOTIFICATIONS_PER_CYCLE", "5") or "5")
        timeout = float(os.environ.get("MONITOR_REQUEST_TIMEOUT", "30") or "30")
        profile_feed_limit = int(os.environ.get("EIS_PROFILE_FEED_LIMIT", "5") or "5")
    except ValueError:
        raise MonitoringConfigurationError("Числовые MONITOR_* параметры содержат неверное значение.") from None
    if interval < 60 or interval > 86400:
        raise MonitoringConfigurationError("MONITOR_INTERVAL_SECONDS должен быть от 60 до 86400.")
    if max_items < 1 or max_items > 100:
        raise MonitoringConfigurationError("MONITOR_MAX_ITEMS должен быть от 1 до 100.")
    if max_notifications < 1 or max_notifications > 20:
        raise MonitoringConfigurationError("MONITOR_MAX_NOTIFICATIONS_PER_CYCLE должен быть от 1 до 20.")
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
        raise MonitoringConfigurationError("MONITOR_REQUEST_TIMEOUT должен быть от 0 до 120 секунд.")
    if profile_feed_limit < 1 or profile_feed_limit > 20:
        raise MonitoringConfigurationError("EIS_PROFILE_FEED_LIMIT должен быть от 1 до 20.")

    urls = _urls(os.environ.get("EIS_RSS_URLS", ""))
    ca_raw = (os.environ.get("EIS_CA_BUNDLE_FILE") or os.environ.get("GIGACHAT_CA_BUNDLE_FILE") or "").strip()
    ca_path = Path(ca_raw).expanduser() if ca_raw else None
    if ca_path and not ca_path.is_file():
        raise MonitoringConfigurationError("Файл EIS_CA_BUNDLE_FILE не найден.")
    try:
        configure_http_environment()
    except ValueError as error:
        raise MonitoringConfigurationError(str(error)) from None

    return MonitoringSettings(
        enabled=_bool("MONITORING_ENABLED", False),
        interval_seconds=interval,
        max_items=max_items,
        max_notifications_per_cycle=max_notifications,
        request_timeout=timeout,
        eis_rss_urls=urls,
        eis_223_enabled=_bool("EIS_223_ENABLED", False),
        b2b_center_enabled=_bool("B2B_CENTER_ENABLED", False),
        tektorg_public_enabled=_bool("TEKTORG_PUBLIC_ENABLED", False),
        mikroton_tender_enabled=_bool("MIKROTON_TENDER_ENABLED", False),
        gpb_etp_public_enabled=_bool("GPB_ETP_PUBLIC_ENABLED", False),
        lenobl_small_public_enabled=_bool("LENOBL_SMALL_PUBLIC_ENABLED", False),
        nmck_native_public_enabled=_bool("NMCK_NATIVE_PUBLIC_ENABLED", False),
        stan_commercial_public_enabled=_bool("STAN_COMMERCIAL_PUBLIC_ENABLED", False),
        south_ural_public_enabled=_bool("SOUTH_URAL_PUBLIC_ENABLED", False),
        ru_dagestan_public_list_enabled=_bool("RU_DAGESTAN_PUBLIC_LIST_ENABLED", False),
        ru_samara_public_list_enabled=_bool("RU_SAMARA_PUBLIC_LIST_ENABLED", False),
        kavkaz_rf_firstparty_enabled=_bool("KAVKAZ_RF_FIRSTPARTY_ENABLED", False),
        ru_background_catalog_enabled=_bool("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", False),
        eis_direct_enabled=_bool("EIS_DIRECT_ENABLED", False),
        eis_system_trust_enabled=_bool("EIS_SYSTEM_TRUST_ENABLED", False),
        eis_44_html_enabled=_bool("EIS_44_HTML_ENABLED", False),
        cis_md_elicitatie_enabled=_bool("VALYQON_CIS_MD_ELICITATIE_ENABLED", False),
        cis_az_azeristilik_enabled=_bool("VALYQON_CIS_AZ_AZERISTILIK_ENABLED", False),
        cis_az_adif_small_enabled=_bool("VALYQON_CIS_AZ_ADIF_SMALL_ENABLED", False),
        eis_223_rss_urls=_urls(os.environ.get("EIS_223_RSS_URLS", "")),
        eis_223_profile_feeds_enabled=_bool("EIS_223_PROFILE_FEEDS_ENABLED", False),
        profile_feeds_enabled=_bool("EIS_PROFILE_FEEDS_ENABLED", True),
        profile_feed_limit=profile_feed_limit,
        ca_bundle_file=ca_path.resolve() if ca_path else None,
    )
