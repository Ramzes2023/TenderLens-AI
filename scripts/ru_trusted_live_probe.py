"""Operator-triggered, fixed-host HTTPS diagnostics for public Russian procurement.

Main-branch-only workflow: never execute PR code on a personal self-hosted runner.
No browser/captcha/auth/proxies, no unrestricted URL input or redirect following.
No data stored. This diagnoses reachability, NOT successful tender ingestion.
"""
from __future__ import annotations

import http.client
import json
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import re
import socket
import ssl
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 15

@dataclass(frozen=True)
class Target:
    host: str
    path: str
    mode: str = "html"

# Immutable allowlist. User controls only a choice from these labels.
TARGETS = {
    "b2b_office": Target("www.b2b-center.ru", "/search/industry/ofis/"),
    "fabrikant_44": Target("44.fabrikant.ru", "/44/catalog/procedure"),
    "roseltorg": Target("www.roseltorg.ru", "/procedures/search"),
    "lenobl": Target("zakupki.lenreg.ru", "/Search/NewRequests"),
    "vologda": Target("szvo.gov35.ru", "/web/gz/em_reestr"),
    "gpb_rss": Target("etpgpb.ru", "/procedures.rss", "rss"),
    "rzd_eshop": Target("eshoprzd.ru", "/"),
    "tektorg": Target("www.tektorg.ru", "/223-fz/procedures"),
    # Legacy selection label, but the live published register uses the same official
    # 44.fabrikant.ru publisher as fabrikant_44; never count as a second feed.
    "fabrikant_44_mirror": Target("44.fabrikant.ru", "/44/catalog/procedure/published"),
    "fabrikant_223_mirror": Target("soap2.fabrikant.ru", "/223/catalog/procedure/finished"),
    "tatarstan_trading": Target("etpzakupki.tatar", "/app/SearchLots/"),
    "samara_small": Target("webtorgi.samregion.ru", "/smallpurchases"),
    "sverdlovsk_small": Target("torgi.egov66.ru", "/smallpurchases/GzwSP/NoticesGrid"),
    "bashkortostan_small": Target("zakaz.bashkortostan.ru", "/quotation-requests/new"),
    "yanao_small": Target("zakupki.yanao.ru", "/vitriny-zakupok/oos-rks-001-001"),
    "moscow_suppliers": Target("zakupki.mos.ru", "/"),
    "moscow_oblast_small": Target("easuz.mosreg.ru", "/for-business"),
    "lot_online": Target("tender.lot-online.ru", "/search"),
    "rts_tomsk_small": Target("region70.rts-tender.ru", "/"),
    "rts_dagestan_small": Target("marketrd.rts-tender.ru", "/"),
    "rts_omsk_small": Target("zmo-omsk.rts-tender.ru", "/"),
    "rts_yaroslavl_small": Target("market-yaroslavl.rts-tender.ru", "/"),
    "sber_berezka": Target("agregatoreat.ru", "/"),
    "tender_pro": Target("www.tender.pro", "/api/tenders/list"),
    "smolensk_small": Target("goszakupki.admin-smolensk.ru", "/smallpurchases/GzwSP/NoticesGrid"),
    "petrozavodsk_small": Target("eshop-ptz.ru", "/"),
    "yaroslavl_small": Target("zakupki.yarregion.ru", "/purchasesoflowvolume-asp/"),
    "voronezh_small": Target("goszakupki.govvrn.ru", "/"),
    "udmurtia_small": Target("wt.udmr.ru", "/"),
    "moscow_oblast_market": Target("market.mosreg.ru", "/"),
    "torgi_online_commercial": Target("etp.etptorgionline.ru", "/app/section/commerc/SearchLots/page"),
    "r_tender_commercial": Target("etp.r-tender.ru", "/app/section/kommerctorg/SearchLots/page"),
    # Official public grid is an accessibility probe, not evidence of tender details.
    "dagestan_official_small": Target("goszakaz.e-dag.ru", "/smallpurchases/GzwSP/NoticesGrid"),
    "tver_official_small": Target("gostorgi.tverreg.ru", "/smallpurchases/Menu/Page/1"),
    "spb_official_eshop": Target("estore.gz-spb.ru", "/electronicshop/catalog/procedure/"),
    # Caucasus original small-purchase candidates: reachability ONLY, never a tender count.
    # Ossetia: Republic government Resolution No. 151 (2023-04-25).
    "ossetia_official_small": Target("15.portalregion.ru", "/"),
    # Stavropol official committee refers to RTS regional small-purchases market.
    "stavropol_rts_small": Target("market26.rts-tender.ru", "/"),
}

# Extra official GPB endpoints are intentionally NOT in batch_priority:
# operator must choose one fixed label per approved main-only manual run.
# Official GPB documentation lists /procedures/ and /procedures.rss;
# new.etpgpb.ru serves the published page with the same section.
# Accessibility is not proof of genuine original detail or ingestion.
ON_DEMAND_TARGETS = {
    "gpb_public_html": Target("etpgpb.ru", "/procedures/"),
    "gpb_new_public_html": Target("new.etpgpb.ru", "/procedures/"),
    "gpb_new_rss": Target("new.etpgpb.ru", "/procedures.rss", "rss"),
    # Accredited GPB state procurement registry; 44-FZ cross-posts with EIS.
    "gpb_gos44_html": Target("gos.etpgpb.ru", "/44/catalog/procedure"),
    # Official EIS root is a transport/TLS observation only. It does not
    # establish a valid regional RSS feed or any original procurement.
    "eis_official_home": Target("zakupki.gov.ru", "/"),
}

class UnsafeAddress(RuntimeError):
    pass

def checked_ips(host: str) -> list[str]:
    records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    addresses = sorted({item[4][0] for item in records})
    if not addresses or len(addresses) > 32:
        raise UnsafeAddress("DNS answer size invalid")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise UnsafeAddress("Non-public DNS address")
    # Prefer IPv4 to avoid relying on IPv6 availability on a WSL runner.
    return sorted(addresses, key=lambda ip: ipaddress.ip_address(ip).version)

class VerifiedIPHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str):
        super().__init__(host, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
        self.pinned_ip = ip

    def connect(self):
        # Pin TCP peer to previously public-IP-checked DNS result; TLS SNI and
        # hostname certificate verification still use the exact allowlisted host.
        sock = socket.create_connection((self.pinned_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise

def read_public(target: Target) -> tuple[str, bytes]:
    if (not re.fullmatch(r"[a-z0-9.-]{5,253}", target.host)
            or not target.path.startswith("/") or "?" in target.path
            or "#" in target.path or "\\" in target.path
            or "//" in target.path):
        raise ValueError("Unapproved source target")
    last_error = None
    for ip in checked_ips(target.host)[:2]:
        conn = VerifiedIPHTTPSConnection(target.host, ip)
        try:
            conn.request("GET", target.path, headers={
                "Accept": "application/rss+xml,application/xml,text/xml" if target.mode == "rss" else "text/html",
                "Accept-Encoding": "identity",
                "User-Agent": "Mozilla/5.0 (compatible; VALYQON-RU-ReadOnlyAudit/1.0)",
                "Connection": "close",
            })
            response = conn.getresponse()
            if response.status != 200:
                print("RU_PROBE_HTTP_STATUS=" + str(response.status))
                raise ValueError("Non-200 official endpoint")
            mime = response.getheader("content-type", "").lower()
            if target.mode == "rss":
                if not any(s in mime for s in ("xml", "rss")):
                    raise ValueError("Not XML/RSS content type")
            elif "html" not in mime:
                raise ValueError("Not HTML content type")
            contents = response.read(MAX_BYTES + 1)
            if not contents or len(contents) > MAX_BYTES:
                raise ValueError("Official response empty or oversized")
            return mime, contents
        except (OSError, ssl.SSLError, TimeoutError) as error:
            last_error = error
        finally:
            conn.close()
    if last_error is not None:
        raise last_error
    raise ValueError("No verified official document")

def describe(mode: str, payload: bytes) -> dict[str, int]:
    if mode == "rss":
        # Even a real HTTP 200 must not qualify a DTD, entity or login XML
        # document as the official public procurement RSS/Atom channel.
        upper = payload.upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise ValueError("Untrusted RSS document declaration")
        root = ET.fromstring(payload)
        if root.tag not in {"rss", "{http://www.w3.org/2005/Atom}feed"}:
            raise ValueError("Not an RSS or Atom feed")
        return {"rss_items": len(root.findall("./channel/item")), "atom_items": len(root.findall("{http://www.w3.org/2005/Atom}entry"))}
    raw = payload.decode("utf-8-sig", "replace")
    return {
        "anchor_tokens": len(re.findall(r"<a\b", raw, flags=re.I)),
        "uuid_tokens": len(set(re.findall(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", raw, flags=re.I))),
        "procurement_number_tokens": len(set(re.findall(r"(?<!\d)\d{19}(?!\d)", raw))),
    }


# Five independent sources requiring real procurement-release proof; labels
# map only to published first-party transport targets. Ingushetia's registered
# Fabrikant mirror is a 44-FZ EIS crosspost; Chechnya's EIS HOME confirms only
# origin HTTPS, not a region-filtered feed, EIS card or downstream ingestion.
RECOVERY_FIVE = {
    "ingushetia": TARGETS["fabrikant_44_mirror"],
    "chechnya": ON_DEMAND_TARGETS["eis_official_home"],
    "roseltorg": TARGETS["roseltorg"],
    "gpb": TARGETS["gpb_rss"],
    "tektorg": TARGETS["tektorg"],
}


def priority_five_network() -> int:
    """Bounded main-only trusted transport evidence, *not* source acceptance."""
    if set(RECOVERY_FIVE) != {"ingushetia", "chechnya", "roseltorg", "gpb", "tektorg"}:
        print("RU_FIVE=BLOCKED_ALLOWLIST")
        return 2

    def once(entry):
        label, target = entry
        try:
            mime, body = read_public(target)
            observed = describe(target.mode, body)
            return {"source": label, "status": "HTTPS_VISIBLE_NOT_INGESTED",
                    "bytes": len(body), "document_tokens": observed}
        except (OSError, ValueError, UnsafeAddress, ET.ParseError, ssl.SSLError) as error:
            return {"source": label, "status": "BLOCKED",
                    "failure_class": type(error).__name__}

    # Exactly 5 immutable first-party endpoints, <= 4 concurrent. Each pin
    # checks ALL DNS IPs as public, retains hostname-verified TLS and refuses
    # redirects. No PR code, user queries, credentials or subscriber messages.
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(once, RECOVERY_FIVE.items()))
    for item in results:
        print("RU_FIVE_SOURCE=" + json.dumps(item, sort_keys=True))
    visible = sum(v["status"] == "HTTPS_VISIBLE_NOT_INGESTED" for v in results)
    print(f"RU_FIVE_FIRSTPARTY_HTTPS_VISIBLE={visible}/5")
    print("RU_FIVE_ORIGINAL_DETAIL_VERIFIED=NO")
    print("RU_FIVE_WORKER_SQL_ACCEPTED=NO")
    print("RU_FIVE_REAL_TELEGRAM_ACK=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0 if visible == len(RECOVERY_FIVE) else 2


def batch_priority() -> int:
    # A bounded read-only operator survey, not 24 working procurement connectors.
    # Only immutable allowlisted labels are scheduled. No tenant or production data.
    if len(TARGETS) != 37:
        print("RU_BATCH=BLOCKED_TARGET_SET")
        return 2

    def once(label: str) -> dict[str, object]:
        try:
            target = TARGETS[label]
            mime, body = read_public(target)
            counts = describe(target.mode, body)
            return {"source": label, "status": "HTTPS_VISIBLE_NOT_INGESTED",
                    "bytes": len(body), "counts": counts}
        except (OSError, ValueError, UnsafeAddress, ET.ParseError, ssl.SSLError) as error:
            return {"source": label, "status": "BLOCKED", "failure_class": type(error).__name__}

    # At most four concurrent allowlisted fixed reads (two labels may share
    # an official publisher host), max two pinned public IP attempts per label,
    # 2 MiB per response and strict certificate-verified HTTPS.
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(once, tuple(TARGETS)))
    for result in results:
        print("RU_BATCH_SOURCE=" + json.dumps(result, sort_keys=True))
    passed = sum(item["status"] == "HTTPS_VISIBLE_NOT_INGESTED" for item in results)
    print(f"RU_BATCH_HTTPS_VISIBLE={passed}/{len(TARGETS)}")
    print("RU_BATCH_NOTICE_DETAIL_VERIFIED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0 if passed == len(TARGETS) else 2


def main(label: str) -> int:
    if label == "priority_five_network":
        return priority_five_network()
    if label == "batch_priority":
        return batch_priority()
    if label not in TARGETS and label not in ON_DEMAND_TARGETS:
        print("RU_PROBE=REJECTED_UNKNOWN_SOURCE")
        return 2
    target = TARGETS[label] if label in TARGETS else ON_DEMAND_TARGETS[label]
    print("RU_PROBE_SOURCE=" + label)
    try:
        mime, body = read_public(target)
        print("RU_PROBE_BYTES=" + str(len(body)))
        for key, value in describe(target.mode, body).items():
            print("RU_PROBE_" + key.upper() + "=" + str(value))
        print("RU_PROBE=HTTPS_READ_ONLY_PASS_NOT_INGESTION")
        print("PRODUCTION_CHANGED=NO")
        return 0
    except (OSError, ValueError, UnsafeAddress, ET.ParseError, ssl.SSLError) as error:
        print("RU_PROBE_BLOCKED_CLASS=" + type(error).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Supply exactly one allowlisted source ID")
    raise SystemExit(main(sys.argv[1]))
