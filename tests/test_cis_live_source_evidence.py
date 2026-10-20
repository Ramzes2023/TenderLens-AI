"""Offline test of source count admission: NEVER substitutes for hosted live jobs."""
from types import SimpleNamespace
import pytest
from scripts.cis_live_source_evidence import classify_source_batch


def result(source, n):
    return {
        "schema": 1, "source_id": source, "fetched_count": n,
        "accepted_count": n, "inserted_count": n,
        "updated_count": 0, "skipped_count": 0,
    }


def test_only_adif_may_complete_a_verified_empty_official_active_offer_set():
    assert classify_source_batch("az_adif_small", result("az_adif_small", 0), []) == "verified_empty"
    for source in ("md_elicitatie", "az_azeristilik"):
        with pytest.raises(AssertionError, match="mandatory"):
            classify_source_batch(source, result(source, 0), [])


def test_nonempty_firstparty_rows_still_prove_real_worker_counts():
    for source in ("az_adif_small", "md_elicitatie", "az_azeristilik"):
        rows = [SimpleNamespace(identity=(source, "id-1"))]
        assert classify_source_batch(source, result(source, 1), rows) == "active"


@pytest.mark.parametrize("mutation", [
    {"fetched_count": 1},
    {"accepted_count": 1},
    {"inserted_count": 1},
    {"skipped_count": 1},
    {"updated_count": 1},
    {"source_id": "md_elicitatie"},
    {"schema": 2},
])
def test_empty_is_never_accepted_on_bad_worker_result(mutation):
    report = {**result("az_adif_small", 0), **mutation}
    with pytest.raises(AssertionError):
        classify_source_batch("az_adif_small", report, [])


def test_duplicate_active_records_are_not_accepted():
    x = SimpleNamespace(identity=("az_adif_small", "same"))
    with pytest.raises(AssertionError, match="Duplicated"):
        classify_source_batch("az_adif_small", result("az_adif_small", 2), [x, x])


def test_closed_official_2026_tenders_are_not_resurrected_into_user_feed():
    from datetime import date
    from app.sources.az_adif_small import parse_public_articles, BUYER
    html = (
        "<html><article><p>" + BUYER +
        " mətbəə məhsullarının satınalınması ilə bağlı kotirovka sorğusu elan edir."
        "</p><p>Təkliflər 19 oktyabr 2026-cı il saat 12:00-dək qəbul olunur."
        "</p><p>Elanın yerləşdirilmə tarixi: 02.10.2026</p>"
        '<a href="https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx">'
        "Kotirovka sorğusu</a></article></html>"
    )
    assert len(parse_public_articles(html, today=date(2026,10,18))) == 1
    assert parse_public_articles(html, today=date(2026,10,20)) == []
