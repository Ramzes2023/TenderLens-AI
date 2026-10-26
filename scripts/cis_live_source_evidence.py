"""Classify *real* completed fenced source jobs, with explicit valid-empty ADIF.

This code neither probes the network nor fabricates tenders. For ADIF, the
official parser rejects undated/malformed pages and may correctly return an
empty active offer set after deadlines. Every caller must require a real,
successful Worker claim before invoking this function.
"""
SOURCES = frozenset({"az_adif_small", "md_elicitatie", "az_azeristilik"})


def classify_source_batch(source_id, report, rows):
    if source_id not in SOURCES or type(report) is not dict or type(rows) is not list:
        raise AssertionError("Untrusted source batch")
    if report.get("source_id") != source_id or report.get("schema") != 1:
        raise AssertionError("Worker source identity or schema mismatch")
    names = ("fetched_count", "accepted_count", "inserted_count",
             "updated_count", "skipped_count")
    if any(type(report.get(key)) is not int or report[key] < 0 for key in names):
        raise AssertionError("Worker count fields missing or invalid")
    if (report["fetched_count"] != len(rows)
            or report["accepted_count"] != len(rows)
            or report["inserted_count"] != len(rows)
            or report["updated_count"] != 0
            or report["skipped_count"] != 0):
        raise AssertionError("Worker did not persist every genuine notice exactly once")
    if not rows:
        if source_id != "az_adif_small":
            raise AssertionError("No real active procurement in mandatory source")
        return "verified_empty"
    if len({item.identity for item in rows}) != len(rows):
        raise AssertionError("Duplicated persisted real source identities")
    return "active"
