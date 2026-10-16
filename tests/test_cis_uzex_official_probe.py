"""Offline strict parser and transport-safety contracts; never count as live proof."""
import io
import json
import unittest
from urllib.error import HTTPError, URLError

from scripts.cis_uzex_official_probe import (
    API_URL,
    MAX_BYTES,
    TIMEOUT_SECONDS,
    inspect_json,
    make_request,
    probe,
    validate_notice,
)


VALID = {
    "id": 510591,
    "name": "Maxsus uskunalar bilan jihozlangan xizmat mototsikllarini yetkazib berish",
    "customer_name": "ГУВД г.Ташкента",
    "start_date": "2026-09-10T10:38:42+05:00",
    "end_date": "2026-09-28T10:38:42+05:00",
}


class Reply:
    status = 200
    headers = {"Content-Type": "application/json;charset=UTF-8"}

    def __init__(self, data):
        self.payload = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.payload.close()

    def read(self, n):
        return self.payload.read(n)


class Opener:
    def __init__(self, data=None, failure=None, response=None):
        self.data = data
        self.failure = failure
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.failure:
            raise self.failure
        if self.response:
            return self.response
        return Reply(self.data)


class UzexProbeContracts(unittest.TestCase):
    def test_pinned_official_host_and_post_body(self):
        request = make_request(1)
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {
            "TypeId": 1, "From": 1, "To": 20, "System_Id": 0,
        })
        self.assertTrue(request.full_url.startswith("https://"))
        self.assertFalse(request.has_header("Authorization"))
        for bad in (-1, 0, 3, 999):
            with self.assertRaises(ValueError):
                make_request(bad)

    def test_valid_complete_notice_requires_all_fields(self):
        self.assertTrue(validate_notice(VALID))
        self.assertTrue(inspect_json(json.dumps([VALID]).encode())["verified"])
        for key in ("id", "name", "customer_name", "start_date", "end_date"):
            damaged = dict(VALID)
            damaged.pop(key)
            self.assertFalse(validate_notice(damaged), key)

    def test_uzex_public_schema_uses_seller_name_for_publishing_entity(self):
        observed = dict(VALID)
        observed["seller_name"] = observed.pop("customer_name")
        self.assertTrue(validate_notice(observed))
        observed["seller_name"] = ""
        self.assertFalse(validate_notice(observed))

    def test_reject_incomplete_spa_banner_or_fake_json(self):
        for candidate in ([], ["loading"], {"data": [{"id": 510591}]},
                          {"data": "loading"}, {"data": [{"id": 1111, "name": "Loading"}]}):
            self.assertFalse(inspect_json(json.dumps(candidate).encode()).get("verified"))
        self.assertFalse(inspect_json(b"<html>200</html>")["verified"])
        self.assertFalse(validate_notice({**VALID, "id": True}))
        self.assertFalse(validate_notice({**VALID, "id": "https://attacker.example"}))

    def test_transport_complete_response_is_real_only_when_http_json(self):
        opener = Opener(json.dumps([VALID]).encode())
        output = probe(1, opener)
        self.assertTrue(output["verified"])
        self.assertEqual(output["complete_notices"], 1)
        self.assertFalse(output.get("production_activation_allowed", False))
        self.assertEqual(opener.requests[0][1], TIMEOUT_SECONDS)
        self.assertEqual(opener.requests[0][0].get_method(), "POST")

    def test_http_and_network_fail_closed(self):
        for problem in (HTTPError(API_URL, 403, "Forbidden", {}, None), URLError("DNS")):
            output = probe(2, Opener(failure=problem))
            self.assertFalse(output["verified"])
            self.assertFalse(output["reachable"])
        class NoJsonReply(Reply):
            headers = {"Content-Type": "text/html"}
        self.assertEqual(probe(1, Opener(response=NoJsonReply(b"[]")))["reason"],
                         "non_json_content_type")

    def test_hard_body_limit(self):
        output = probe(1, Opener(b"x" * (MAX_BYTES + 1)))
        self.assertEqual(output["reason"], "oversized_response")
        self.assertFalse(output["verified"])


if __name__ == "__main__":
    unittest.main()
