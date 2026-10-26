"""Strict current live proof: first-party Dagestan public-grid metadata survives Worker/SQL.

Not an individual detail verification and not a production notification.
A genuine upstream grid with no parseable amount/deadline must fail, not
be represented as a successful new field integration.
"""
import json

from scripts.ci_ru_dagestan_public_list_sql import proof


def main():
    try:
        evidence = proof()
        if (evidence["live_official_list_rows"] < 2
                or evidence["native_public_amounts_observed"] < 1
                or evidence["native_public_deadlines_observed"] < 1):
            print("RU_DAG_PUBLIC_FIELDS=BLOCKED_NO_LIVE_GRID_FIELD_EVIDENCE")
            print("PRODUCTION_CHANGED=NO")
            return 2
    except Exception as error:
        print("RU_DAG_PUBLIC_FIELDS=BLOCKED_" + type(error).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_DAG_PUBLIC_FIELDS_EVIDENCE=" + json.dumps(
        evidence, sort_keys=True, ensure_ascii=False))
    print("RU_DAG_PUBLIC_FIELDS=PASS_PUBLIC_LIST_ONLY")
    print("INDIVIDUAL_DETAIL_VERIFIED=NO")
    print("REAL_TELEGRAM_RECEIPT_VERIFIED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
