import pytest
from app.sources.stan_commercial_public import parse_list, canonical, verify_detail, LIST_URL, StanCommercialPublicSource

def listing():
    return ('''<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>
<a href="/etp/AAaaBB12">Поставка угля каменного для нужд предприятия</a>
<a href="/etp/RScxkWBC">№ ЗК-2026-000020</a>
<a href="/etp/RScxkWBC"><h2>Поставка пожарных шкафов</h2></a>
<a href="/etp/Aabbcc12">№ ЗК-2026-000016</a>
<a href="/etp/Aabbcc12">Строительно-монтажные работы по водоснабжению</a>
<a href="https://outside.example/etp/Abcdef12">№ ЗК-2026-000099</a>''').encode()

def detail(n,t,section="Коммерческая закупка"):
    return f"<div>{section}</div><h1>{t}</h1><div>Номер процедуры</div><div>{n}</div>".encode()

def test_first_party_commercial_two_links_not_eis_mirrors():
    r=parse_list(listing())
    assert len(r)==2
    assert [x[0] for x in r]==["ЗК-2026-000020","ЗК-2026-000016"]
    assert all(x[2].startswith(LIST_URL+"/") for x in r)

@pytest.mark.parametrize("url",[
    "https://evil.example/etp/RScxkWBC",
    "http://stantorgi.ru/etp/RScxkWBC",
    "https://stantorgi.ru.evil.test/etp/RScxkWBC",
    "/etp/RScxkWBC?secret=1",
    "/etp/RScxkWBC#secret",
    "/etp/../../etc",
    "//evil.test/etp/RScxkWBC"])
def test_untrusted_urls_never_accepted(url):
    assert canonical(url) is None

def test_independent_title_and_number_required():
    n,t,u=parse_list(listing())[0]
    assert verify_detail(detail(n,t),n,t,u)==(n,t,u)
    for bad in (detail("ЗК-2026-000021",t),detail(n,"Другая процедура"),
                detail(n,t,"Закупка по 223-ФЗ"),f"<h1>{t}</h1><script>Номер процедуры {n} Коммерческая закупка</script>".encode()):
        with pytest.raises(ValueError):
            verify_detail(bad,n,t,u)

def test_fail_closed_on_eis_only():
    with pytest.raises(ValueError):
        parse_list('<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>'.encode('utf-8'))



def test_adapter_real_shape_follows_only_commercial_canonical_details(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.stan_commercial_public as module
    docs = []
    mapping = {item[2]: detail(item[0],item[1]) for item in parse_list(listing())}
    class Fake:
        async def get(self, url):
            docs.append(url)
            if url == LIST_URL:
                body = listing()
            else:
                assert url in mapping
                body = mapping[url]
            return SimpleNamespace(content=body,headers={"content-type":"text/html"},raise_for_status=lambda:None)
    @asynccontextmanager
    async def fake_client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        yield Fake()
    monkeypatch.setattr(module,"source_client",fake_client)
    notices=asyncio.run(StanCommercialPublicSource().fetch(limit=2))
    assert [n.external_id for n in notices] == ["ЗК-2026-000020","ЗК-2026-000016"]
    assert all(n.initial_price is None and n.deadline is None for n in notices)
    assert len(docs)==3
