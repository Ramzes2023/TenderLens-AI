"""Offline-only review guard for the 5-source Russian Windows audit.

A successful syntax or inspection test does NOT prove official publisher access,
any original tender's persistence, or an actual Telegram message delivery.
"""
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts" /
          "ru_five_windows_live_audit.ps1")


def test_operator_audit_is_main_only_and_explicitly_requires_live_proof_optin():
    data = SCRIPT.read_text("utf-8")
    assert "if ($RunLiveProofs)" in data
    assert "REJECTED_NOT_REVIEWED_MAIN" in data
    assert "-cne 'main'" in data
    assert "RU_FIVE_SOURCE_WORKER_TESTS=NOT_REQUESTED" in data
    assert "RU_FIVE_CUSTOMER_TELEGRAM_ACK=NOT_VERIFIED" in data
    assert "PRODUCTION_CHANGED=NO" in data
    assert data.count("priority_five_network") == 1
    assert "-m scripts.ru_trusted_live_probe priority_five_network" in data


def test_only_five_fixed_source_modules_and_no_dynamic_code_execution():
    data = SCRIPT.read_text("utf-8")
    modules = (
        "ci_ru_ingushetia_live_worker.py",
        "ci_ru_chechnya_eis_real_worker.py",
        "ci_ru_roseltorg_real_worker.py",
        "ci_ru_gpb_public_worker.py",
        "ci_ru_tektorg_fenced_acceptance.py",
    )
    for module in modules:
        assert data.count("Script = '" + module + "'") == 1
    assert data.count("Module = 'scripts.ci_") == 5
    for forbidden in (
        "Invoke-Expression", "Invoke-RestMethod", "Invoke-WebRequest",
        "Start-Process", "Set-ExecutionPolicy", "git checkout",
        "git fetch", "git pull", "git clone", "git reset",
        "--insecure", "verify=False", "curl -k",
        "RU_CHECHNYA_E2E_TEST_CHAT_ID', 'Process')",  # no-op marker? revised below
    ):
        # The token is present only in the explicitly managed no-send
        # credentials block, not as a network operation.
        if forbidden.startswith("RU_CHECHNYA_"):
            continue
        assert forbidden not in data
    assert "if (-not (Test-Path -LiteralPath $modulePath -PathType Leaf))" in data


def test_no_actual_telegram_receipt_can_be_inferred_from_local_proof():
    data = SCRIPT.read_text("utf-8")
    assert "RU_FIVE_ORIGINAL_" in data
    assert "PASS_ISOLATED_WORKER_SQL" in data
    assert "NOT_IN_MAIN" in data
    assert "'RU_CHECHNYA_E2E_TEST_BOT_TOKEN'" in data
    assert "'RU_CHECHNYA_E2E_TEST_CHAT_ID'" in data
    assert "NOT_VERIFIED" in data
