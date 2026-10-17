"""Offline listing parsing contracts. Fixtures do NOT count as live tender proof."""
import pytest
from scripts.research_ru_sverdlovsk_public import listing_evidence

def fixture():
    return ("""<div>Реестровый номер ИМЗ-2026-2-044-011567
Дата публикации 12.10.2026
Начальная (максимальная) цена контракта, руб. 499 000.00
Объект закупки Котел водогрейный
Заказчик ГБУ Свердловской области</div>
<div>Реестровый номер ИМЗ-2026-2-223-012012
Дата публикации 12.10.2026
Объект закупки Поставка картриджей и фотобарабанов для принтеров
Заказчик ГАУЗ Свердловской области</div>
<script>Реестровый номер ИМЗ-2026-2-223-999999
Объект закупки Запрещенная подставная запись Заказчик</script>""").encode()

def test_genuine_official_pairs_only_from_visible_html():
    n,linked=listing_evidence(fixture())
    assert len(n)==2
    assert n["ИМЗ-2026-2-044-011567"]=="Котел водогрейный"
    assert n["ИМЗ-2026-2-223-012012"]=="Поставка картриджей и фотобарабанов для принтеров"
    assert linked==0

def test_unknown_and_js_fake_source_blocked():
    assert listing_evidence(b"<html><div>Welcome</div></html>")[0]=={}
    assert listing_evidence(b"<script>Реестровый номер ИМЗ-2026-2-044-011567 Объект закупки Товар Заказчик</script>")[0]=={}

def test_ambiguous_public_id_disallowed():
    data=('Реестровый номер ИМЗ-2026-2-044-011567 Объект закупки Котел водогрейный Заказчик '
          'Реестровый номер ИМЗ-2026-2-044-011567 Объект закупки Другая продукция Заказчик').encode()
    with pytest.raises(ValueError):
        listing_evidence(data)

def test_unsafe_inputs_fail():
    with pytest.raises(ValueError):
        listing_evidence(b"")
    with pytest.raises(ValueError):
        listing_evidence(b"\x00")
