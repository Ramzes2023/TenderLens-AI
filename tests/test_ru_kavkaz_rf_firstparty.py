"""Offline hostile HTML never counts as Kavkaz.RF source live acceptance."""
from __future__ import annotations
import asyncio

import httpx
import pytest

from app.sources.kavkaz_rf_firstparty import (
    HOST, LIST_URL, SOURCE_ID, KavkazRfFirstpartySource, _canonical,
    parse_listing, parse_detail,
)

A = "АЭФ-ДВА-397"
B = "ЗКЭФ-ДЭУК-1540"
TA = "Право заключения договора на оказание аудиторских услуг по оценке реализации программы"
TB = "Право заключения договора на поставку с установкой горных тормозов для снегоходов"
PA = "/purchases_sales/zakupki/tekushchie-/auktsiony-v-elektronnoy-forme/pravo-zaklyucheniya-dogovora_515335/"
PB = "/purchases_sales/zakupki/tekushchie-/zapros-kotirovok-v-elektronnoy-forme/8%20pravo-zaklyucheniya-dogovora/"


def index(a=A, b=B):
    return (f"""<html><table>
     <tr><th>№ извещения</th><th>Предмет закупки</th></tr>
     <tr><td>{a}</td><td><a href="{PA}">{TA}</a></td><td>Аукцион</td></tr>
     <tr><td>{b}</td><td><a href="{PB}">{TB}</a></td><td>Запрос котировок</td></tr>
    </table></html>""").encode()


def original(number, title, amount="1 764 000,00"):
    return (f"""<html><script>window.fake = "СТРАННЫЕ ДАННЫЕ";</script>
     <h1>{title}</h1><dl>
     <dt>Способ закупки:</dt><dd>Аукцион в электронной форме</dd>
     <dt>№ Извещения:</dt><dd>{number}</dd>
     <dt>ДАТА ОПУБЛИКОВАНИЯ:</dt><dd>08.10.2026</dd>
     <dt>Статус:</dt><dd>Прием заявок до 26.10.2026</dd>
     <dt>Начальная (максимальная) цена договора:</dt><dd>{amount} рублей</dd>
     </dl></html>""").encode()


def test_two_genuine_shaped_firstparty_rows_and_independent_details():
    rows = parse_listing(index())
    assert len(rows) == 2
    assert {number for number, _, _ in rows} == {A, B}
    for number, title, url in rows:
        result = parse_detail(original(number, title), number=number, title=title, url=url)
        assert result.source == SOURCE_ID
        assert result.external_id == result.tender_number == number
        assert result.title == title
        assert result.url == url
        assert result.initial_price == 1764000.0 and result.currency == "RUB"
        assert result.published_at == "2026-10-08"
        assert result.deadline == "2026-10-26"


@pytest.mark.parametrize("href", [
    "http://xn--80aafvlc.xn--p1ai" + PA,
    "https://xn--80aafvlc.xn--p1ai.evil.example" + PA,
    "https://evil.example" + PA,
    "//evil.example" + PA,
    "https://user:pass@xn--80aafvlc.xn--p1ai" + PA,
    PA + "?token=secret",
    PA + "#fragment",
    PA.replace("pravo-zaklyucheniya", "%2fpravo-zaklyucheniya"),
    "../../admin",
    "/purchases_sales/zakupki/tekushchie-/",
    "/purchases_sales/zakupki/tekushchie-/zapros-kotirovok/page",
    "https://xn--80aafvlc.xn--p1ai:8443" + PA,
])
def test_reject_external_redirect_and_unsafe_detail_links(href):
    assert _canonical(href) is None


def test_duplicate_unknown_and_script_injection_fail_closed():
    with pytest.raises(ValueError):
        parse_listing(b"<html>Login</html>")
    with pytest.raises(ValueError):
        parse_listing(index().replace(B.encode(), A.encode()).replace(PB.encode(), (PA + "?x=1").encode()))
    with pytest.raises(ValueError):
        parse_listing(b"<script>" + index() + b"</script>")
    with pytest.raises(ValueError):
        parse_listing(index().replace(A.encode(), b"<b>X</b>"))
    assert parse_listing(index(), limit=1)[0][0] == A


def test_detail_mismatch_price_and_native_number_must_fail():
    number, title, url = parse_listing(index())[0]
    for body in (
        original("АЭФ-ДВА-398", title),
        original(number, "Право заключения договора на совершенно другую работу"),
        original(number, title).replace("№ Извещения".encode(), "Номер".encode()),
        original(number, title).replace("1 764 000,00".encode(), "Не указано".encode()),
        original(number, title).replace("08.10.2026".encode(), "НЕТ ДАТЫ".encode()),
        b"<script>" + original(number, title) + b"</script>",
    ):
        with pytest.raises(ValueError):
            parse_detail(body, number=number, title=title, url=url)


def test_live_adapter_contract_disallows_invalid_config_and_unbounded_limits():
    with pytest.raises(ValueError):
        KavkazRfFirstpartySource(timeout=0)
    with pytest.raises(ValueError):
        KavkazRfFirstpartySource(timeout=42)
    with pytest.raises(ValueError):
        asyncio.run(KavkazRfFirstpartySource().fetch(0))
    assert HOST == "xn--80aafvlc.xn--p1ai"
    assert LIST_URL.endswith("/purchases_sales/zakupki/tekushchie-/")


def test_synthetic_mock_transport_cannot_imply_real_availability(monkeypatch):
    import app.sources.kavkaz_rf_firstparty as source
    requests = []

    def transport(request):
        requests.append((request.method, str(request.url)))
        if str(request.url) == LIST_URL:
            return httpx.Response(200, content=index(), headers={"content-type": "text/html"})
        if str(request.url).endswith(PA):
            return httpx.Response(200, content=original(A, TA), headers={"content-type": "text/html"})
        if str(request.url).endswith(PB):
            return httpx.Response(200, content=original(B, TB), headers={"content-type": "text/html"})
        return httpx.Response(404)

    monkeypatch.setattr(source, "source_client", lambda **kwargs: httpx.AsyncClient(
        transport=httpx.MockTransport(transport), follow_redirects=False
    ))
    notices = asyncio.run(KavkazRfFirstpartySource().fetch(2))
    assert len(notices) == 2
    assert len(requests) == 3
    assert all(method == "GET" and url.startswith("https://" + HOST + "/") for method, url in requests)
    # Fixture-only proof: live acceptance and fenced-worker acceptance are separate.
