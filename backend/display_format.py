"""Display formatting shared by the API and the server-rendered pages.

The directory is stitched together from scrapes, bulk imports and hand entry,
so the same field arrives in several shapes: "74 NORTH ORLANDO AVE" next to
"1155 Grant Avenue", city slugs next to display names. Rendering them as
stored looks broken.

Everything here is read-time only. Stored values are left exactly as written,
so geocoding, duplicate matching and city matching all keep seeing the
original text; only what a person sees is normalised. Every function is
idempotent, which is what makes it safe to apply at any layer.

This lives outside main.py because seo_hubs and kj_site_light render venue
rows directly, and importing main from either would be circular.
"""

import re


US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
}

# Full state names → USPS codes, for address tails like "Punta Gorda, Florida".
US_STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN",
    "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}


# Street-type words, in every spelling the scrapes use, mapped to one display
# form. Abbreviated with a period because that is the convention the app reads
# in; USPS mailing format (no period, all caps) is a different target.
_STREET_TYPES = {
    "avenue": "Ave.", "ave": "Ave.", "av": "Ave.",
    "street": "St.", "str": "St.", "st": "St.",
    "road": "Rd.", "rd": "Rd.",
    "boulevard": "Blvd.", "blvd": "Blvd.", "boul": "Blvd.",
    "drive": "Dr.", "dr": "Dr.", "drv": "Dr.",
    "lane": "Ln.", "ln": "Ln.",
    "court": "Ct.", "ct": "Ct.",
    "circle": "Cir.", "cir": "Cir.",
    "place": "Pl.", "pl": "Pl.",
    "terrace": "Ter.", "ter": "Ter.", "terr": "Ter.",
    "parkway": "Pkwy.", "pkwy": "Pkwy.", "pky": "Pkwy.",
    "highway": "Hwy.", "hwy": "Hwy.",
    "square": "Sq.", "sq": "Sq.",
    "trail": "Trl.", "trl": "Trl.",
    "plaza": "Plz.", "plz": "Plz.",
    "expressway": "Expy.", "expy": "Expy.",
    "turnpike": "Tpke.", "tpke": "Tpke.",
    "causeway": "Cswy.", "cswy": "Cswy.",
    "crossing": "Xing", "xing": "Xing",
    "extension": "Ext.", "ext": "Ext.",
    "way": "Way", "walk": "Walk", "row": "Row", "run": "Run", "loop": "Loop",
    "pike": "Pike", "path": "Path", "mall": "Mall", "alley": "Aly.",
}

_DIRECTIONALS = {
    "north": "N", "n": "N", "south": "S", "s": "S",
    "east": "E", "e": "E", "west": "W", "w": "W",
    "northeast": "NE", "ne": "NE", "northwest": "NW", "nw": "NW",
    "southeast": "SE", "se": "SE", "southwest": "SW", "sw": "SW",
}

_UNIT_TYPES = {
    "suite": "Ste.", "ste": "Ste.",
    "apartment": "Apt.", "apt": "Apt.",
    "building": "Bldg.", "bldg": "Bldg.",
    "floor": "Fl.", "flr": "Fl.",
    "unit": "Unit", "room": "Rm.", "rm": "Rm.", "space": "Spc.",
}

# Tokens that are acronyms, not words, and must not be title-cased.
_KEEP_UPPER = {"US", "SR", "CR", "FM", "PO", "RR", "HC", "USA", "NE", "NW", "SE", "SW"}

_ORDINAL_RE = re.compile(r"^(\d+)(st|nd|rd|th)$", re.I)


def _titlecase_word(word: str) -> str:
    """Title-case one token, leaving the things title-casing usually ruins.

    str.title() turns "O'MALLEY'S" into "O'Malley'S" and "3RD" into "3Rd", both
    of which show up constantly in scraped addresses.
    """
    if not word:
        return word
    upper = word.upper().strip(".")
    if upper in _KEEP_UPPER:
        return upper
    m = _ORDINAL_RE.match(word)
    if m:
        return f"{m.group(1)}{m.group(2).lower()}"
    # A token with no letters (house numbers, ZIPs) is left exactly as is.
    if not any(ch.isalpha() for ch in word):
        return word
    # Mixed letters and digits ("1A", "I-95") read better upper.
    if any(ch.isdigit() for ch in word) and any(ch.isalpha() for ch in word):
        return word.upper()

    def cap_run(run: str) -> str:
        # Only capitalise a post-apostrophe run if it is a real syllable:
        # "O'Malley" yes, the possessive "'s" no.
        return run[:1].upper() + run[1:].lower() if len(run) > 1 else run.lower()

    parts = []
    for i, apostrophe_run in enumerate(word.split("'")):
        parts.append(
            "-".join(
                (h[:1].upper() + h[1:].lower()) if h else h
                for h in apostrophe_run.split("-")
            )
            if i == 0
            else cap_run(apostrophe_run)
        )
    return "'".join(parts)


def _display_address(raw: str | None) -> str | None:
    """Normalise a street address for display.

    The directory is stitched together from scrapes and hand entry, so the same
    field arrives as "74 NORTH ORLANDO AVE, COCOA BEACH, FL 32931" and as
    "1155 Grant Avenue, San Francisco, CA 94133". Rendering both as-is looks
    broken; this settles on one form — mixed case, abbreviated street types.

    Read-time only. The stored value is untouched, so geocoding and duplicate
    matching keep seeing exactly what they were written with.
    """
    if not raw or not raw.strip():
        return raw

    segments = [seg.strip() for seg in raw.split(",")]
    out_segments: list[str] = []

    for seg_i, seg in enumerate(segments):
        tokens = seg.split()
        if not tokens:
            continue
        words = [_titlecase_word(t) for t in tokens]

        # A two-letter state code keeps its case, but only in a trailing
        # segment — "1 Me Ln." should not become "1 ME Ln.".
        if seg_i > 0:
            for i, t in enumerate(tokens):
                if t.upper() in US_STATES and len(t) == 2:
                    words[i] = t.upper()

        # Street types and directionals only mean what they look like inside
        # the street segment. Elsewhere "St" is Saint, as in "St. Louis".
        if seg_i == 0:
            n = len(tokens)
            for i, t in enumerate(tokens):
                key = t.lower().strip(".")
                # Unit designators, anywhere after the house number.
                if key in _UNIT_TYPES and i > 0:
                    words[i] = _UNIT_TYPES[key]
                    continue
                if key in _DIRECTIONALS:
                    # A directional prefix sits between the number and the
                    # street name; a suffix ends the segment. In the middle of
                    # a name ("Lake North Park Dr") it is part of the name.
                    if (i == 1 and n > 2) or i == n - 1:
                        words[i] = _DIRECTIONALS[key]
                    continue
                if key in _STREET_TYPES and i > 0:
                    # Only when it actually terminates the street name — the
                    # rest of the segment must be directionals or unit info.
                    rest = [x.lower().strip(".") for x in tokens[i + 1:]]
                    if all(
                        r in _DIRECTIONALS or r in _UNIT_TYPES
                        or r.startswith("#") or r.isdigit() or len(r) <= 2
                        for r in rest
                    ):
                        words[i] = _STREET_TYPES[key]
        out_segments.append(" ".join(words))

    return ", ".join(out_segments)


# Unit / occupancy designators. Stripped before building a dedup key because
# they are the single most common way one real venue produces two rows —
# "#13&14" and "#1314" are the same suite written by two different scrapes.
# They also break every address parser worth trying: usaddress reads the "&"
# in "#13&14" as a street intersection, and usaddress-scourgify raises
# UnParseableAddressError on it outright. Removing the unit first fixes both,
# and a unit number is not what tells two venues apart anyway.
_UNIT_RE = re.compile(
    r"[,\s]*(?:#|\bapt\.?\b|\bsuite\b|\bste\.?\b|\bunit\b|\bbldg\.?\b|\brm\.?\b)\s*[\w&/\-]*",
    re.I,
)


def canonical_street_key(address: str | None) -> str:
    """Just the street line, canonicalised. No locality.

    Kept separate from canonical_address_key because the locality is exactly
    the part that cannot be trusted: the Fishlips row says Cape Canaveral when
    the bar is in Port Canaveral. Callers that pair this with a proximity
    check get the best of both — the street text agreeing, and the two rows
    actually being in the same place on the ground.
    """
    a = _UNIT_RE.sub("", address or "")
    a = _display_address(a) or ""
    a = a.split(",")[0]
    a = re.sub(r"[^a-z0-9]+", " ", a.lower())
    return re.sub(r"\s+", " ", a).strip()


def canonical_address_key(
    address: str | None, city: str | None = None, state: str | None = None
) -> str:
    """A comparison key for "is this the same street address?".

    Deliberately not a new dependency. libpostal is the well-known answer and
    genuinely the best of them, but it ships source-only — it means building a
    C library and a ~2GB model on the deploy host. usaddress-scourgify is pure
    Python and does good USPS Pub 28 normalisation, but it is US-only and
    raises on messy scraped input.
    
    Measured against scourgify on real rows, this produces identical street
    keys, because _display_address already does the same normalisation work
    (NORTH -> N, Avenue -> Ave.) — and unlike scourgify it still yields a key
    for a non-US address instead of throwing.

    Punctuation is flattened so "US-1" and "US 1" agree. Not a display value;
    never show this to anyone.
    """
    return (
        f"{canonical_street_key(address)}|{_normalize_city(city)}"
        f"|{(state or '').strip().upper()}"
    )


def _display_city(raw: str | None, address: str | None = None) -> str | None:
    """Turn a stored city value into something fit to show a person.

    The column holds URL slugs for a good chunk of the table ("san-francisco"),
    which render as-is on the venue card. The address usually carries the same
    city properly cased ("1155 Grant Ave, San Francisco, CA 94133"), so prefer
    that when a comma-separated part of it matches the stored value; otherwise
    title-case the slug.

    Read-time only — the stored value is left alone, so nothing that matches or
    dedupes on it shifts under us.
    """
    if not raw or not raw.strip():
        return raw
    value = raw.strip()
    normalized = _normalize_city(value)

    if address:
        for part in address.split(","):
            part = part.strip()
            if part and _normalize_city(part) == normalized:
                return part

    # Already looks like a display name (has capitals and no slug separators).
    if value != value.lower() and "-" not in value and "_" not in value:
        return value

    return " ".join(w.capitalize() for w in normalized.split()) or value


def _normalize_city(value: str | None) -> str:
    """Reduce a city to space-separated lowercase words for comparison.

    The city column is not clean. A scraped import wrote URL slugs
    ("san-francisco", "melbourne-vic-au") alongside properly cased names
    ("Chicago", "West Melbourne") and bare lowercase ("austin"), so the same
    place exists under several spellings. Comparing raw strings meant
    "San Francisco" found nothing while "san-francisco" found seventeen.

    Punctuation becomes a word break, so a slug and a typed name converge on
    the same token string.
    """
    if not value:
        return ""
    out = []
    for ch in value.lower():
        out.append(ch if ch.isalnum() else " ")
    return " ".join("".join(out).split())
