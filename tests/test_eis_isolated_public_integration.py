"""EIS official RSS public integration offline safety; no live supplier claims."""
from datetime import datetime, timedelta, timezone
import json

import pytest
import yaml

from app.api.public_eis_identity import accepted_eis_original
from app.api.public_source_deadline import eligible_published_deadline
from app.api.isolated_public_sources import approved_public_source_keys
from app.sources.eis_deadlines import result_deadline
from app.sources.ru_cycle import RU_APPROVED_SOURCES

N44 = "0316300145126000012"
N223 = "32616521305"


def notice(source="eis", number=N44):
    path = ("/223/purchase/public/purchase/info/common-info.html"
            if source == "eis_223"
            else "/epz/order/notice/ezt20/view/common-info.html")
    return {
        "source": source, "external_id": number,
        "tender_number": number, "title": "Поставка оборудования",
        "url": "https://zakupki.gov.ru" + path + "?regNumber=" + number,
    }


@pytest.mark.parametrize("source,number", [("eis", N44), ("eis_44_html", N44), ("eis_223", N223)])
def test_official_identity_only(source, number):
    good = notice(source, number)
    assert accepted_eis_original(good)
    for bad in (
        {**good, "url": good["url"].replace("zakupki.gov.ru", "evil.invalid")},
        {**good, "url": good["url"].replace("https:", "http:")},
        {**good, "url": good["url"] + "&more=yes"},
        {**good, "url": good["url"].replace(number, "123456")},
        {**good, "tender_number": number + "1"},
        {**good, "source": "different"},
    ):
        assert not accepted_eis_original(bad)
    if source == "eis_44_html":
        assert not accepted_eis_original({**good, "external_id": "wrong"})


def test_223_source_result_deadline_without_claiming_moscow_timezone():
    source = (
        "Дата окончания из фильтра: 01.01.2020 01:00 "
        "Найденный результат: 223-ФЗ Дата и время окончания подачи заявок: "
        "10.12.2026 19:45"
    )
    assert result_deadline(source) == "10.12.2026 19:45"
    assert result_deadline("Дата и время окончания подачи заявок: 31.02.2026 12:00") is None
    assert result_deadline(source + " Окончание подачи заявок: 11.12.2026 12:00") is None
    assert result_deadline("Найденный результат: Дата размещения: 10.12.2026 19:45") is None
    assert result_deadline(None) is None


def test_current_eis_deadline_never_assumes_unstated_offset():
    now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    for key in ("eis", "eis_223"):
        assert eligible_published_deadline(key, "10.12.2026 19:45", now=now)
        assert not eligible_published_deadline(key, "30.10.2026 20:00", now=now)
        assert not eligible_published_deadline(key, "31.02.2026 20:00", now=now)
        assert not eligible_published_deadline(key, "30.10.2026", now=now)
        assert not eligible_published_deadline(key, "unknown", now=now)


def test_eis_public_flags_are_explicit_not_an_eis_profile_default():
    flags = {
        "MIKROTON_TENDER_ENABLED": "true",
        "STAN_COMMERCIAL_PUBLIC_ENABLED": "true",
    }
    allowed = approved_public_source_keys(flags)
    assert "eis" not in allowed and "eis_223" not in allowed
    flags["EIS_RSS_PUBLIC_ENABLED"] = "true"
    flags["EIS_223_PUBLIC_ENABLED"] = "true"
    allowed = approved_public_source_keys(flags)
    assert {"eis", "eis_223"}.issubset(allowed)
    with pytest.raises(RuntimeError):
        approved_public_source_keys({**flags, "EIS_223_PUBLIC_ENABLED": "yes"})
    assert "eis" not in RU_APPROVED_SOURCES and "eis_223" not in RU_APPROVED_SOURCES


def test_eis_compose_does_not_change_prod_volume_or_unapproved_delivery():
    data = yaml.safe_load(open("ops/public_sources/compose.eis-rss.yaml", encoding="utf-8"))
    assert set(data["services"]) == {"guest-sources", "worker", "scheduler", "enqueue"}
    for service in data["services"].values():
        assert not service.get("volumes") and not service.get("ports")
        env = service["environment"]
        assert env["EIS_RSS_PUBLIC_ENABLED"] == "true"
        assert env["EIS_223_PUBLIC_ENABLED"] == "true"
        assert "TELEGRAM_BOT_TOKEN" not in env
    assert data["services"]["worker"]["environment"]["EIS_DIRECT_ENABLED"] == "true"


def test_current_real_eis_anonymous_search_rejects_wrong_origin(tmp_path):
    from app.api.guest_search_routes import search_persisted_notices
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.sources.opportunities import OpportunityRepository

    now = datetime.now(timezone.utc)
    db = Database(DatabaseSettings("eis-isolated-test", tmp_path / "isolated.sqlite"))
    try:
        OpportunityRepository(db).initialize()
        for no, base in enumerate((notice(), {**notice(), "url": "https://evil.invalid/tender"})):
            row = dict(base, external_id=f"eis-{no}",
                       deadline=(now + timedelta(days=4)).isoformat())
            with db.connect() as conn:
                conn.execute(
                    "INSERT INTO source_opportunities "
                    "(source_id,external_id,notice_json,connector_version,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?)",
                    ("eis", row["external_id"], json.dumps(row, ensure_ascii=False),
                     "connector-sync-v1:eis:adapter-r1", now.isoformat(), now.isoformat()),
                )
                conn.commit()
        found = search_persisted_notices(
            db, "оборудования", active_only=True, now=now,
            allowed_sources=frozenset({"eis"})
        )
        assert found["shown"] == 1
        assert set(found["results"][0]) == {
            "title", "initial_price", "currency", "deadline"
        }
    finally:
        db.close()
