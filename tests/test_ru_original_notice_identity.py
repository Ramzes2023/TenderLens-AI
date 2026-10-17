"""RU cross-platform original notice identity must never fake publishers."""
import pytest

from app.sources.models import TenderNotice
from app.sources.ru_notice_identity import original_notice_key, distinct_original_count


def notice(source, external_id, number=None, title="Поставка товара"):
    return TenderNotice(source=source, external_id=external_id,
        tender_number=number, title=title, url="https://example.org/public")


def test_fabrikant_44_and_eis_44_copies_share_exact_proven_original():
    original="0373100100726000010"
    rows=[
        notice("eis_44_html",original,original),
        notice("fabrikant_44_public",original,original),
        notice("eis",original,original),
    ]
    assert {original_notice_key(row) for row in rows} == {("eis_44",original)}
    assert distinct_original_count(rows)=={
        "record_count":3,"adapter_key_count":3,
        "original_notice_count":1,"cross_source_duplicate_count":2,
    }


def test_eis_223_11_digit_shared_by_two_eis_adapters():
    eid="32616478602"
    left=notice("eis_223",eid,eid)
    right=notice("eis",eid,eid)
    assert original_notice_key(left)==original_notice_key(right)==("eis_223",eid)


def test_native_platform_procurement_numbers_not_misclassified_as_eis():
    native=[
        notice("stan_commercial_public","ЗК-2026-000020","ЗК-2026-000020"),
        notice("nmck_native_public","20261000009","20261000009М"),
        notice("lenobl_small_public","some-local-123","123"),
    ]
    assert distinct_original_count(native)["original_notice_count"]==3
    assert [original_notice_key(n)[0] for n in native]==[
        "stan_commercial_public","nmck_native_public","lenobl_small_public",
    ]


def test_non_eis_19_digits_cannot_be_inferred_from_unverified_platform():
    eid="0373100100726000010"
    russian_unknown=notice("roseltorg_public","SP12345678",eid)
    gpb=notice("gpb_etp_public",eid,eid)
    assert original_notice_key(russian_unknown)==("roseltorg_public","SP12345678")
    assert original_notice_key(gpb)==("gpb_etp_public",eid)
    assert distinct_original_count([russian_unknown,gpb])["original_notice_count"]==2


def test_local_19_digit_mirror_requires_eis_source_evidence():
    num="0373100100726000010"
    assert original_notice_key(notice("fabrikant_44_public",num,num)) == ("eis_44",num)
    assert original_notice_key(notice("fabrikant_44_public","local",num)) == ("eis_44",num)
    assert original_notice_key(notice("fabrikant_44_public","local","invalid")) == ("fabrikant_44_public","local")


@pytest.mark.parametrize("bad",[
    notice("eis",""),
    notice("eis"," 123"),
    notice("eis", "bad\x00id"),
    notice("EIS", "someid"),
])
def test_invalid_identifiers_rejected(bad):
    with pytest.raises(ValueError):
        original_notice_key(bad)


def test_no_records_means_no_proof_of_sources():
    assert distinct_original_count([])=={
        "record_count":0,"adapter_key_count":0,
        "original_notice_count":0,"cross_source_duplicate_count":0,
    }
