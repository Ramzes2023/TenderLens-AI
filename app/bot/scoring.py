"""Telegram rendering for deterministic company-profile scoring."""
from app.scoring.models import ScoringResult
from .tender import split_messages

STATUS_ICON = {
    "matched": "✅",
    "partial": "🟡",
    "failed": "❌",
    "not_scored": "⚪",
}


def _points(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def format_scoring(result: ScoringResult) -> list[str]:
    if result.fit_score is None:
        score_line = "🎯 СООТВЕТСТВИЕ ПРОФИЛЮ: недостаточно данных"
    else:
        score_line = f"🎯 СООТВЕТСТВИЕ ПРОФИЛЮ: {result.fit_score:g}/100"

    sections = [
        score_line,
        f"Профиль: {result.profile_name}\nВерсия правил: {result.profile_version}",
        f"📊 Полнота извлечённых данных: {result.completeness_percent}%",
    ]

    rendered_criteria: list[str] = []
    for item in result.criteria:
        icon = STATUS_ICON[item.status]
        if item.status == "not_scored":
            heading = f"{icon} {item.label} — не оценивалось"
        else:
            heading = f"{icon} {item.label} — {_points(item.earned_points)}/{item.weight}"
        block = heading + "\n" + item.explanation
        if item.evidence:
            block += "\n" + "\n".join("• " + evidence for evidence in item.evidence)
        rendered_criteria.append(block)
    sections.append("Критерии:\n\n" + "\n\n".join(rendered_criteria))

    if result.stop_factors:
        sections.append("🛑 Стоп-факторы по правилам профиля:\n" +
                        "\n".join("• " + item for item in result.stop_factors))
    else:
        sections.append("🛑 Стоп-факторы по правилам профиля: не обнаружены.")

    if result.document_risks:
        sections.append("⚠️ Риски из документа:\n" +
                        "\n".join("• " + item for item in result.document_risks))

    if result.missing_information:
        sections.append("ℹ️ Не хватает данных:\n" +
                        "\n".join("• " + item for item in result.missing_information[:20]))

    sections.append(
        "Score показывает совместимость с заданным профилем компании. "
        "Это не вероятность победы и не рекомендация участвовать или отказаться."
    )
    return split_messages("\n\n".join(sections))
