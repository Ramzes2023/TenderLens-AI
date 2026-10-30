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

def test_single_non_eis_commercial_card_is_admissible_for_detail_verification():
    # An official listing may have one true commercial tender and many
    # 223-FZ EIS mirrors. Require independent number+title links for that one.
    page = ('''<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>
<a href="/etp/AAaaBB12">Поставка угля каменного для нужд предприятия</a>
<a href="/etp/RScxkWBC">№ ЗК-2026-000020</a>
<a href="/etp/RScxkWBC"><h2>Поставка пожарных шкафов</h2></a>''').encode()
    record = parse_list(page)
    assert len(record) == 1
    assert record[0][0] == "ЗК-2026-000020"
    assert verify_detail(detail(record[0][0], record[0][1]),
                         *record[0]) == record[0]
    with pytest.raises(ValueError):
        verify_detail(detail(record[0][0], record[0][1], "Закупка по 223-ФЗ"),
                      *record[0])


def test_single_number_without_independent_title_is_not_enough():
    with pytest.raises(ValueError):
        parse_list(b'<a href="/etp/RScxkWBC">test</a>')


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
            elif url == LIST_URL + "?page=2":
                body = b'<a href="/etp/AAaaBB12">No eligible commercial</a>'
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
    assert len(docs)==4
    assert docs[:2] == [LIST_URL, LIST_URL + "?page=2"]


def test_second_page_commercial_original_retrieved_after_eis_only_first_page(monkeypatch):
    """Both listing URLs must be fetched before strict independent detail."""
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.stan_commercial_public as module

    number = "ЗК-2026-000016"
    title = "Выполнение комплекса строительно-монтажных работ и водоотведения"
    url = LIST_URL + "/TDQJKSbF"
    first = '''<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>
<a href="/etp/AAaaBB12">223-ФЗ поставка материалов и оборудования</a>'''.encode()
    second = (f'<a href="/etp/TDQJKSbF">№ {number}</a>'
              f'<a href="/etp/TDQJKSbF"><h2>{title}</h2></a>').encode()
    original = (
        f"<h1>{title}</h1><div>Коммерческая закупка</div>"
        f"<div>Номер процедуры</div><div>{number}</div>"
        "<div>Наименование заказчика</div><div>ООО СК Основа</div>"
        "<div>Дата и время окончания подачи заявок</div>"
        "<div>11.11.2026 08:00 (МСК)</div>"
    ).encode()
    calls = []

    class Fake:
        async def get(self, actual):
            calls.append(actual)
            mapping = {LIST_URL: first, LIST_URL + "?page=2": second, url: original}
            assert actual in mapping, "unexpected extra HTTP request"
            return SimpleNamespace(content=mapping[actual],
                                   headers={"content-type": "text/html"},
                                   raise_for_status=lambda: None)

    @asynccontextmanager
    async def fake_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Fake()

    monkeypatch.setattr(module, "source_client", fake_client)
    notices = asyncio.run(StanCommercialPublicSource().fetch(limit=2))
    assert len(notices) == 1
    assert notices[0].external_id == number
    assert notices[0].url == url
    assert notices[0].customer == "ООО СК Основа"
    assert notices[0].deadline == "2026-11-11T08:00:00+03:00"
    assert calls == [LIST_URL, LIST_URL + "?page=2", url]


def test_both_pages_eis_only_still_fail_closed(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.stan_commercial_public as module

    only_eis = ('''<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>
<a href="/etp/AAaaBB12">223-ФЗ выполнение работ</a>''').encode()
    calls = []

    class Fake:
        async def get(self, url):
            calls.append(url)
            assert url in (LIST_URL, LIST_URL + "?page=2")
            return SimpleNamespace(content=only_eis,
                                   headers={"content-type": "text/html"},
                                   raise_for_status=lambda: None)
    @asynccontextmanager
    async def fake_client(**kwargs):
        yield Fake()
    monkeypatch.setattr(module, "source_client", fake_client)
    with pytest.raises(ValueError, match="No commercial originals"):
        asyncio.run(StanCommercialPublicSource().fetch(limit=2))
    assert calls == [LIST_URL, LIST_URL + "?page=2"]


def test_duplicate_commercial_original_across_pages_only_fetched_once(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.stan_commercial_public as module
    record = ('''<a href="/etp/RScxkWBC">№ ЗК-2026-000020</a>
<a href="/etp/RScxkWBC"><h2>Поставка пожарных шкафов</h2></a>''').encode()
    calls = []
    class Fake:
        async def get(self,url):
            calls.append(url)
            return SimpleNamespace(
                content=record if "?" in url or url==LIST_URL else detail(
                    "ЗК-2026-000020","Поставка пожарных шкафов"),
                headers={"content-type":"text/html"},
                raise_for_status=lambda: None)
    @asynccontextmanager
    async def fake_client(**kwargs):
        yield Fake()
    monkeypatch.setattr(module,"source_client",fake_client)
    notices = asyncio.run(StanCommercialPublicSource().fetch(limit=2))
    assert len(notices)==1
    assert calls==[LIST_URL,LIST_URL+"?page=2",LIST_URL+"/RScxkWBC"]
