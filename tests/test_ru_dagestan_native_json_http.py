"""Offline fixtures for original Dagestan public JSON envelope (never live proof)."""
import copy

import pytest
from datetime import date
from scripts.research_ru_dagestan_native_json_http import settings, real_list_proof, one_month_ago


def sample_data():
    return {"page": 0, "totalRows": 200, "items": [
        {
            "name": "Поставка оборудования для больницы", "number": "ИМЗ-2026-010012",
            "uchr_sname": "Городская больница",
            "link": "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/5611345",
            "summa": 112000, "collecting_enddate": "25.10.2026",
        },
        {
            "name": "Ремонт кровли районной школы", "number": "ИМЗ-2026-010013",
            "uchr_sname": "Районная школа",
            "link": "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/5611196",
            "summa": 212000, "collecting_enddate": "28.10.2026",
        },
    ]}


def test_fixed_public_settings_match_observed_anonymous_browser_structure():
    obj = settings("18.09.2026")
    assert obj["page"] == 0
    assert obj["rp"] == 10
    assert obj["totalRows"] == 0
    assert obj["sortField"] == "pub_date"
    assert obj["sortDir"] == "desc"
    assert obj["filter"] == {"dtDatePubBegin": {
        "PName": "dtDatePubBegin", "PType": "Date", "PValue": "18.09.2026",
    }}
    assert obj["localFilter"] == []
    assert obj["rpList"] == [10, 20, 30]
    assert one_month_ago(date(2026, 10, 18)) == "18.09.2026"
    assert one_month_ago(date(2024, 3, 31)) == "29.02.2024"
    assert one_month_ago(date(2026, 1, 31)) == "31.12.2025"
    with pytest.raises(ValueError):
        settings(None)
    with pytest.raises(ValueError):
        settings("31.02.2026")
    with pytest.raises(ValueError):
        settings("private-data")


def test_two_distinct_firstparty_original_list_identities_are_research_only():
    assert real_list_proof(sample_data()) == [
        ("5611345", "ИМЗ-2026-010012"),
        ("5611196", "ИМЗ-2026-010013"),
    ]


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(items=[]),
    lambda d: d.update(totalRows=0),
    lambda d: d["items"][1].update(link="https://external.example/smallpurchases/GzwSP/5611196"),
    lambda d: d["items"][1].update(link="https://goszakaz.e-dag.ru/smallpurchases/GzwSP/5611345"),
    lambda d: d["items"][0].update(number="ИМЗ-2026-010013"),
    lambda d: d["items"][0].update(name="<script>FAKE TENDER</script>"),
    lambda d: d["items"][0].update(uchr_sname=""),
    lambda d: d["items"][0].update(link="javascript:alert(1)"),
    lambda d: d["items"][0].update(link="/smallpurchases/GzwSP/5611345?password=secret"),
])
def test_forged_duplicate_or_noncanonical_original_list_is_rejected(mutate):
    doc = copy.deepcopy(sample_data())
    mutate(doc)
    with pytest.raises(ValueError):
        real_list_proof(doc)
