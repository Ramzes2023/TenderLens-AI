"""Country policy v1: exact explicit location values, never region/currency guesses.

ISO alpha-2 whitelist; alpha-3/name aliases are deliberately a supported subset.
Unknown aliases stay unmapped. Code/name disagreement in one location conflicts;
different locations can legitimately have different countries.
"""

# Date normalization is separately versioned from the country policy.
from .dates import DATE_POLICY, CalendarDate, NormalizedDate, UTCInstant, normalize_date, stored_date

COUNTRY_VERSION = "iso3166-location-v1"
ISO_ALPHA2 = frozenset("""AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP
KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY
MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY
QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW""".split())
ALIASES = {
    "usa": "US", "united states": "US", "united states of america": "US",
    "gbr": "GB", "united kingdom": "GB", "uk": "GB",
    "aus": "AU", "australia": "AU", "can": "CA", "canada": "CA",
    "ita": "IT", "italy": "IT", "fra": "FR", "france": "FR",
    "deu": "DE", "germany": "DE", "nzl": "NZ", "new zealand": "NZ",
    "zaf": "ZA", "south africa": "ZA", "ind": "IN", "india": "IN",
    "rus": "RU", "russia": "RU", "kaz": "KZ", "kazakhstan": "KZ",
}


def country_code(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    return value.upper() if value.upper() in ISO_ALPHA2 else ALIASES.get(value.casefold())


def normalize_countries(locations):
    """Each location is a list of synonymous code/name evidence values."""
    countries, evidence = set(), []
    conflict = False
    for index, location in enumerate(location for location in locations if location):
        codes = {country_code(entry['value']) for entry in location}
        known = codes - {None}
        if len(known) > 1:
            conflict = True
        else:
            countries.update(known)
        evidence.extend({**entry, 'location': index, 'code': country_code(entry['value'])} for entry in location)
    ambiguous = any(isinstance(e['value'], str) and e['value'].strip().casefold() in
                    {'congo', 'korea', 'virgin islands'} for e in evidence)
    invalid = any(not isinstance(e['value'], str) or not e['value'].strip() for e in evidence)
    status = ('conflicting' if conflict else 'missing' if not evidence else
              'ambiguous' if ambiguous else 'invalid' if invalid else
              'unmapped' if not countries else 'partial' if any(e['code'] is None for e in evidence)
              else 'multi_country' if len(countries) > 1 else 'verified')
    return {'version': COUNTRY_VERSION, 'semantics': 'place_of_performance',
            'codes': [] if conflict else sorted(countries), 'status': status, 'evidence': evidence}
