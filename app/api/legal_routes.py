"""Fail-closed Russian legal publication: never present unapproved drafts as terms."""
from __future__ import annotations
import os
import hashlib
import json
from html import escape
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["legal"])
VERSION = "2026-10-17-v1"
REQUIRED_SETTINGS = (
    "VALYQON_LEGAL_ENTITY", "VALYQON_LEGAL_ADDRESS", "VALYQON_LEGAL_EMAIL",
    "VALYQON_LEGAL_REGISTRATION", "VALYQON_LEGAL_DATA_REGION",
    "VALYQON_LEGAL_RETENTION",
)

def legal_ready() -> bool:
    return (os.environ.get("VALYQON_LEGAL_APPROVED", "").lower() == "true"
            and all(os.environ.get(key, "").strip() for key in REQUIRED_SETTINGS))

def legal_version() -> str:
    # Proof of the exact published operator + document body; never reuse a
    # version when the operator changes the legal publication configuration.
    payload = {
        "revision": VERSION,
        "operator": {key: os.environ.get(key, "") for key in REQUIRED_SETTINGS},
        "pages": PAGES,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return VERSION + "-" + digest

PAGES = {
 "offer": ("Публичная оферта", """
 <h2>Предмет договора</h2><p>VALYQON AI предоставляет доступ к функциям
 поиска, предварительного скоринга и мониторинга закупок в рамках действующего
 тарифа. Данные из источников необходимо проверять самостоятельно на официальных
 сайтах. Сервис не гарантирует выигрыш тендера или своевременное получение сведений.</p>
 <h2>Оплата</h2><p>Стоимость тарифа, сроки, условия подписки, отмены и возвратов
 указываются в заказе до оплаты. Без утверждённых условий оплачиваемых планов
 приём платежей не допускается.</p>"""),
 "privacy": ("Политика конфиденциальности и обработки персональных данных", """
 <h2>Какие данные</h2><p>E-mail, хеш пароля, информация о сессиях, журнал
 согласий, сведения профиля компании, сохранённые закупки, сообщения поддержки
 и настройки уведомлений.</p>
 <h2>Зачем</h2><p>Регистрация и исполнение договора, защита учётной записи,
 аналитика закупок и отправка отдельно включённых сервисных уведомлений.
 Реклама направляется только при дополнительном добровольном согласии.</p>
 <h2>Хранение</h2><p>Правила хранения: {retention}. Регион размещения
 первичных баз данных: {region}. Фактические процессоры, AI-провайдеры и
 трансграничные передачи требуют отдельной проверки оператором.</p>
 <h2>Права</h2><p>Запросы о доступе, исправлении, удалении и отзыве согласий
 направляются оператору. Отзыв не отменяет обработку при наличии иного
 законного основания.</p>"""),
 "personal-data": ("Отдельное согласие на обработку персональных данных", """
 <p>Соглашаюсь на обработку указанных мной контактных, учётных данных и
 добровольно загружаемых сведений в целях предоставления сервиса, защиты
 аккаунта и связи по вопросам сервиса. Обработка включает сбор, запись,
 систематизацию, хранение, использование, уточнение и удаление,
 в том числе автоматизированно.</p>
 <p>Срок хранения: {retention}. Согласие можно отозвать через контакт
 оператора. Законные основания, не зависящие от согласия, сохраняются.</p>"""),
 "marketing": ("Отдельное согласие на рекламу", """
 <p>Добровольно соглашаюсь получать маркетинговые сообщения о VALYQON AI
 по электронной почте. Это согласие не требуется для регистрации;
 отзыв допускается в любой момент через адрес оператора или ссылку
 отписки в рекламном письме.</p>"""),
}

@router.get("/legal/{document}", response_class=HTMLResponse, include_in_schema=False)
def legal_page(document: str):
    if document not in PAGES:
        raise HTTPException(404, "Legal document not found.")
    if not legal_ready():
        raise HTTPException(503, "Legal documents are awaiting approval.")
    title, text = PAGES[document]
    region = escape(os.environ["VALYQON_LEGAL_DATA_REGION"])
    retention = escape(os.environ["VALYQON_LEGAL_RETENTION"])
    details = " ".join(
        "<p>" + escape(label) + ": " + escape(os.environ[key]) + "</p>"
        for label,key in (
            ("Оператор", "VALYQON_LEGAL_ENTITY"),
            ("Регистрационные сведения", "VALYQON_LEGAL_REGISTRATION"),
            ("Адрес", "VALYQON_LEGAL_ADDRESS"),
            ("Адрес для обращений", "VALYQON_LEGAL_EMAIL"),
        )
    )
    html = ("<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>" + escape(title) + " — VALYQON AI</title></head><body>"
            "<main style='max-width:850px;margin:auto;padding:32px;font:16px/1.6 system-ui'>"
            "<h1>" + escape(title) + "</h1><p>Редакция " + legal_version() + "</p>"
            + text.format(region=region, retention=retention) + details
            + "</main></body></html>")
    return HTMLResponse(html, headers={"Cache-Control":"public, max-age=300"})
