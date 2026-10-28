"""Public date-field research is not ingestion, expiry or live-site proof."""
from scripts.research_ru_lenobl_official_deadline import (
    classify_visible_deadline, LABELS,
)


def test_publisher_label_and_timed_value_reported_as_unverified_candidate():
    payload=(
        "<html><h1>Запрос предложений для нужд учреждения</h1>"
        "<p>Срок окончания подачи оферт: 07.11.2026 14:30</p>"
        "<p>Дата создания: 28.10.2026</p></html>"
    ).encode("utf8")
    report=classify_visible_deadline(payload)
    assert report["visible_label_count"]==1
    assert report["date_field_candidates"][0]["field"]==LABELS[0]
    assert report["date_field_candidates"][0]["nearby_dates"][0]=="07.11.2026 14:30"
    assert report["is_verified_submission_deadline"] is False


def test_metadata_and_hidden_template_dates_never_invent_deadline():
    payload=(
        "<html><head><title>Срок окончания подачи оферт 31.12.2099</title></head>"
        "<script>Срок окончания подачи оферт 31.12.2099</script>"
        "<template>Срок окончания подачи оферт 31.12.2099</template>"
        "<body><h1>Поставка оборудования</h1>"
        "<p>Дата создания 28.10.2026</p></body></html>"
    ).encode("utf8")
    report=classify_visible_deadline(payload)
    assert report["visible_label_count"]==0
    assert report["page_contains_any_dates"]
    assert report["date_field_candidates"]==[]
    assert report["is_verified_submission_deadline"] is False


def test_unrelated_date_in_window_is_not_auto_promoted():
    payload=(
        "<html><h1>Закупка</h1><p>Окончание подачи предложений "
        "уточняется — дата последней редакции: 05.11.2026</p></html>"
    ).encode("utf8")
    report=classify_visible_deadline(payload)
    assert report["visible_label_count"]==1
    assert report["date_field_candidates"][0]["nearby_dates"]
    assert report["is_verified_submission_deadline"] is False


def test_date_only_never_invents_time_or_zone():
    payload=(
        "<html><h1>Поставка материалов</h1>"
        "<p>Срок окончания подачи оферт: 29.10.2026</p></html>"
    ).encode("utf8")
    report=classify_visible_deadline(payload)
    assert report["date_field_candidates"][0]["nearby_dates"]==["29.10.2026"]
    assert report["is_verified_submission_deadline"] is False
