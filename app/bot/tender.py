"""Plain-text tender presentation; no Markdown interpretation."""
from app.services.tender_analysis import AnalysisResult


def split_messages(text: str, limit: int = 3500) -> list[str]:
    # Telegram counts UTF-16 code units; emojis can consume two units.
    chunks, current, size = [], "", 0
    for line in text.splitlines(keepends=True):
        units = len(line.encode("utf-16-le")) // 2
        if current and size + units > limit:
            chunks.append(current.rstrip())
            current, size = "", 0
        for char in line:
            count = len(char.encode("utf-16-le")) // 2
            if size + count > limit:
                chunks.append(current.rstrip())
                current, size = "", 0
            current += char
            size += count
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def format_tender(result: AnalysisResult) -> list[str]:
    data = result.analysis
    sections = ["📄 ТЕНДЕР"]
    labels = {
        "title": "Название", "customer": "Заказчик", "tender_number": "Номер закупки",
        "initial_price": "💰 НМЦК", "currency": "Валюта",
        "submission_deadline": "📅 Срок подачи", "contract_term": "Срок контракта",
        "delivery_region": "📍 Регион поставки", "delivery_address": "Адрес поставки",
        "bid_security_amount": "🔐 Обеспечение заявки — сумма",
        "bid_security_percent": "Обеспечение заявки — %",
        "contract_security_amount": "🔐 Обеспечение контракта — сумма",
        "contract_security_percent": "Обеспечение контракта — %",
        "procurement_object": "Предмет закупки", "quantity": "Количество",
        "participant_requirements": "📋 Требования к участникам",
        "required_documents": "📎 Необходимые документы",
        "technical_requirements": "⚙️ Технические требования",
        "risks": "⚠️ Потенциальные риски", "important_conditions": "❗ Важные условия",
        "missing_information": "Не найдена информация",
    }
    for field, label in labels.items():
        value = getattr(data, field)
        if value is None or value == [] or value == "":
            continue
        if isinstance(value, list):
            rendered = "\n".join("• " + item for item in value)
        elif isinstance(value, float):
            rendered = format(value, ",.2f").replace(",", " ").rstrip("0").rstrip(".")
        else:
            rendered = str(value)
        sections.append(label + ":\n" + rendered)
    if len(sections) == 1:
        sections.append("В предоставленном тексте факты о тендере не найдены.")
    if result.truncated:
        sections.append("Анализ ограничен начальной частью документа. Условия в остальной части не проверены.")
    sections.append("AI-сводка: сверяйте факты с оригиналом. Решение об участии не принимается.")
    return split_messages("\n\n".join(sections))
