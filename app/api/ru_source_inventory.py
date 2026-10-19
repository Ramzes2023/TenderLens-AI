"""Curated Russian source coverage: research or unmerged PRs, NEVER live adapters.

Items have provenance in GitHub and known fixed public source URLs. Listing them
on a public website is not a readiness, uptime, freshness, or ingestion claim.
Maintain from mainline trusted probe and reviewed Russian source PRs.
"""

from __future__ import annotations

# (key, public title, HTTPS source URL, official institution, focus, GitHub evidence)
RU_STAGED_ADAPTERS = (
    ("fabrikant_44_public","Фабрикант — 44-ФЗ (адаптер в PR)","https://44.fabrikant.ru/44/catalog/procedure", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/95"),
    ("roseltorg_public","Росэлторг — публичные процедуры (адаптер в PR)","https://www.roseltorg.ru/procedures/search", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/101"),
    ("south_ural_public","Южный Урал — региональные и коммерческие малые закупки (адаптер в PR)","https://www.vendorportal.ru/Market/OfferInvitationOpen", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/134"),
)

RU_RESEARCH_TARGETS = (
    ("vologda_small","Вологодская область — малые закупки","https://szvo.gov35.ru/web/gz/em_reestr", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/104"),
    ("gpb_rss_feed","ЭТП Газпромбанка — RSS-канал (исследование)","https://etpgpb.ru/procedures.rss", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/104"),
    ("rzd_eshop","РЖД — электронный магазин малых закупок","https://eshoprzd.ru/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/147"),
    ("fabrikant_44_mirror","Фабрикант — служебный каталог 44-ФЗ (зеркало)","https://soap4.fabrikant.ru/44/catalog/procedure/requestOffer", False,"general","https://github.com/Ramzes2023/TenderLens-AI/blob/main/scripts/ru_trusted_live_probe.py"),
    ("fabrikant_223_mirror","Фабрикант — служебный каталог 223-ФЗ (зеркало)","https://soap2.fabrikant.ru/223/catalog/procedure/finished", False,"general","https://github.com/Ramzes2023/TenderLens-AI/blob/main/scripts/ru_trusted_live_probe.py"),
    ("tatarstan_trading","Татарстан — региональная ЭТП etpzakupki.tatar","https://etpzakupki.tatar/app/SearchLots/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/149"),
    ("sverdlovsk_small","Свердловская область — малые закупки","https://torgi.egov66.ru/smallpurchases/GzwSP/NoticesGrid", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/131"),
    ("bashkortostan_small","Башкортостан — запросы котировок","https://zakaz.bashkortostan.ru/quotation-requests/new", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("yanao_small","ЯНАО — витрина малых закупок","https://zakupki.yanao.ru/vitriny-zakupok/oos-rks-001-001", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("moscow_suppliers","Москва — Портал поставщиков","https://zakupki.mos.ru/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("moscow_oblast_small","Московская область — ЕАСУЗ","https://easuz.mosreg.ru/for-business", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("lot_online","Лот-онлайн — поиск закупок","https://tender.lot-online.ru/search", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("rts_tomsk_small","Томская область — РТС малые закупки","https://region70.rts-tender.ru/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("rts_dagestan_small","Дагестан — РТС электронный магазин","https://marketrd.rts-tender.ru/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/126"),
    ("rts_omsk_small","Омская область — РТС малые закупки","https://zmo-omsk.rts-tender.ru/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("rts_yaroslavl_small","Ярославская область — РТС малые закупки","https://market-yaroslavl.rts-tender.ru/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("sber_berezka","ЕАТ Берёзка — закупки малого объёма","https://agregatoreat.ru/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("tender_pro","Tender.Pro — коммерческие тендеры","https://www.tender.pro/api/tenders/list", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("smolensk_small","Смоленская область — малые закупки","https://goszakupki.admin-smolensk.ru/smallpurchases/GzwSP/NoticesGrid", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/blob/main/scripts/ru_trusted_live_probe.py"),
    ("petrozavodsk_small","Петрозаводск — муниципальный электронный магазин","https://eshop-ptz.ru/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/127"),
    ("yaroslavl_small","Ярославская область — закупки малого объёма","https://zakupki.yarregion.ru/purchasesoflowvolume-asp/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/blob/main/scripts/ru_trusted_live_probe.py"),
    ("voronezh_small","Воронежская область — региональные закупки","https://goszakupki.govvrn.ru/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/blob/main/scripts/ru_trusted_live_probe.py"),
    ("udmurtia_small","Удмуртия — региональные закупки","https://wt.udmr.ru/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/blob/main/scripts/ru_trusted_live_probe.py"),
    ("moscow_oblast_market","Подмосковье — региональный маркетплейс","https://market.mosreg.ru/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/blob/main/scripts/ru_trusted_live_probe.py"),
    ("torgi_online_commercial","Торги-Онлайн — коммерческие торги","https://etp.etptorgionline.ru/app/section/commerc/SearchLots/page", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/123"),
    ("r_tender_commercial","R-Tender — коммерческие торги","https://etp.r-tender.ru/app/section/kommerctorg/SearchLots/page", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/123"),
    ("dagestan_official_small","Дагестан — официальный реестр малых закупок","https://goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesGrid", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/126"),
    ("tver_official_small","Тверская область — официальный реестр малых закупок","https://gostorgi.tverreg.ru/smallpurchases/Menu/Page/1", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/137"),
    ("spb_official_eshop","Санкт-Петербург — официальный электронный магазин малых закупок (проверка доступности)","https://estore.gz-spb.ru/electronicshop/catalog/procedure/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/153"),
    # Validated government authority but no accepted live list→original-detail ingestion.
    ("ossetia_official_small","РСО-Алания — официальный портал малых закупок (исследование)","https://15.portalregion.ru/", True,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/204"),
    ("stavropol_rts_small","Ставропольский край — РТС магазин малых закупок (исследование)","https://market26.rts-tender.ru/", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/204"),
    ("etp_rt","ЭТП РТ — региональные закупки Татарстана","https://etp-rt.ru/search/open", False,"regional_small","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("rftorgi","РФ-Торги — поиск тендеров","https://rftorgi.ru/tenders", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
    ("gazprom_gmt","Газпром — GMT активные тендеры","https://gmt.gazprom.ru/tenders/active/", False,"general","https://github.com/Ramzes2023/TenderLens-AI/pull/99"),
)

__all__ = ["RU_STAGED_ADAPTERS", "RU_RESEARCH_TARGETS"]
