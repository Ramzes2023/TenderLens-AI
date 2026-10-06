
from app.monitoring.service import (
    _term_match,
    prefilter_notice,
)
from app.scoring.models import (
    CompanyProfile,
)
from app.sources.eis_rss import _clean
from app.sources.models import TenderNotice


def profile():
    return CompanyProfile(
        profile_version="keyword-boundary-v1",
        company_name="ALOX Test",
        product_keywords=[
            "gold",
            "silver",
            "precious metals",
            "bullion",
        ],
        search_keywords=[
            "gold",
            "silver",
            "precious metals",
            "bullion",
        ],
    )


def notice(
    external_id,
    summary,
):
    return TenderNotice(
        source="eis",
        external_id=external_id,
        title="Procurement notice",
        url=(
            "https://example.test/"
            + external_id
        ),
        summary=summary,
    )


def test_gold_does_not_match_goldhofer():
    assert not _term_match(
        "Trailer Goldhofer equipment",
        "gold",
    )


def test_gold_does_not_match_golden():
    assert not _term_match(
        "Golden Eagle saw blades",
        "gold",
    )


def test_gold_matches_real_gold():
    assert _term_match(
        "Supply of refined gold bullion",
        "gold",
    )


def test_multiword_phrase_matches():
    assert _term_match(
        "Supply of precious-metals bullion",
        "precious metals",
    )


def test_eis_highlight_does_not_split_goldhofer():
    assert (
        _clean(
            "<b>Gold</b>hofer"
        )
        == "Goldhofer"
    )


def test_eis_highlight_does_not_split_golden():
    assert (
        _clean(
            "<b>Gold</b>en Eagle"
        )
        == "Golden Eagle"
    )


def test_prefilter_rejects_goldhofer():
    assert (
        prefilter_notice(
            notice(
                "goldhofer",
                (
                    "Repair of trailers "
                    "Goldhofer and COMETTO"
                ),
            ),
            profile(),
        )
        is None
    )


def test_prefilter_rejects_golden_eagle():
    assert (
        prefilter_notice(
            notice(
                "golden-eagle",
                (
                    "Saw blades "
                    "Golden Eagle or equivalent"
                ),
            ),
            profile(),
        )
        is None
    )


def test_prefilter_accepts_real_gold():
    assert (
        prefilter_notice(
            notice(
                "real-gold",
                (
                    "Supply of refined gold "
                    "bullion bars"
                ),
            ),
            profile(),
        )
        is not None
    )



def test_russian_inflection_pumps():
    assert _term_match(
        "\u041f\u043e\u0441\u0442\u0430\u0432\u043a\u0430 "
        "\u043d\u0430\u0441\u043e\u0441\u043e\u0432",
        "\u043d\u0430\u0441\u043e\u0441\u044b",
    )


def test_russian_inflection_valves():
    assert _term_match(
        "\u0417\u0430\u043c\u0435\u043d\u0430 "
        "\u043a\u043b\u0430\u043f\u0430\u043d\u043e\u0432",
        "\u043a\u043b\u0430\u043f\u0430\u043d\u044b",
    )


def test_russian_inflection_bearings():
    assert _term_match(
        "\u041f\u0430\u0440\u0442\u0438\u044f "
        "\u043f\u043e\u0434\u0448\u0438\u043f\u043d\u0438\u043a\u043e\u0432",
        "\u043f\u043e\u0434\u0448\u0438\u043f\u043d\u0438\u043a\u0438",
    )


def test_russian_equipment_case():
    assert _term_match(
        "\u041f\u043e\u0441\u0442\u0430\u0432\u043a\u0430 "
        "\u043e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u044f",
        "\u043e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u0435",
    )
