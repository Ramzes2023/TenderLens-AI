"""Read-only regional transport probe is a classification, NEVER ingestion proof."""
import socket

from scripts.ru_regional_public_transport_matrix import TARGETS, main, probe
from scripts.ru_trusted_live_probe import Non200OfficialResponse


def test_only_known_public_publisher_origins_and_fixed_queries():
    assert len(TARGETS)==6
    assert set(t.host for t in TARGETS.values())=={
        "zakupki.gov.ru","44.fabrikant.ru","soap4.fabrikant.ru",
        "webtorgi.samregion.ru",
    }
    assert all(not p.path.startswith("http") and "@" not in p.path and
               "\\" not in p.path and "//" not in p.path for p in TARGETS.values())
    assert TARGETS["ingushetia_eis_rss"].mode=="rss"
    assert TARGETS["chechnya_fabrikant_44"].path.endswith("dir=desc")
    assert TARGETS["chechnya_fabrikant_soap4"].path.endswith("dir=desc")


def test_live_probe_classifies_html_as_visible_not_verified_original():
    def fake(target):
        return "text/html", b"<html><body><a href='/procedure/123'>Tender</a></body></html>"
    result=probe("chechnya_fabrikant_soap4",reader=fake)
    assert result["classification"]=="HTTPS_VISIBLE_NOT_ORIGINAL_VERIFIED"
    assert result["body_bytes"]>0
    assert "structural_tokens" in result
    assert not result.get("source_release_ready",False)


def test_live_probe_cannot_claim_success_on_network_failure():
    def fail(_):
        raise socket.timeout("private request details must not be logged")
    result=probe("chechnya_fabrikant_44",reader=fail)
    assert result=={"label":"chechnya_fabrikant_44",
                    "classification":"BLOCKED","failure_class":"TimeoutError"}
    assert "private request" not in str(result)


def test_live_probe_classifies_non200_only_by_status():
    def fail(_):
        raise Non200OfficialResponse(403)
    result=probe("samara_firstparty_grid",reader=fail)
    assert result=={"label":"samara_firstparty_grid",
                    "classification":"OFFICIAL_HTTP_NON200","status":403}


def test_actual_live_reader_is_not_mocked_by_default():
    from scripts.ru_trusted_live_probe import read_public
    assert probe.__kwdefaults__["reader"] is read_public
