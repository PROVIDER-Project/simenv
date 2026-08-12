"""Verbatim topology snapshot shipped by Issue #23 at commit 5ee637c.

This is historical reference data and must never be updated to match new
behaviour. If a future change makes the contract fail, that change requires
justification.
"""

NODE_META_23: dict[str, dict] = {
    "bra_farmers": {
        "label": "Brazil soy farms",
        "role": "producer",
        "entityIds": ["brazil_farms"],
    },
    "arg_farmers": {
        "label": "Argentina soy farms",
        "role": "producer",
        "entityIds": ["argentina_farms"],
    },
    "usa_farmers": {
        "label": "US soy farms",
        "role": "producer",
        "entityIds": ["us_farms"],
    },
    "wholesalers": {
        "label": "Wholesalers",
        "role": "wholesaler",
        "entityIds": [],
    },
    "feed_traders": {
        "label": "Feed traders",
        "role": "feed_trader",
        "entityIds": [],
    },
    "processors": {
        "label": "EU oil mills",
        "role": "processor",
        "entityIds": ["eu_oil_mills"],
    },
    "feed_manufacturers": {
        "label": "Feed mills",
        "role": "feed_manufacturer",
        "entityIds": ["feed_mills"],
    },
    "eu_farmers": {
        "label": "EU livestock farms",
        "role": "consumer",
        "entityIds": ["poultry_farms", "pig_farms", "dairy_farms"],
    },
}

PORT_META_23: dict[str, dict] = {
    "transport_sa_santos": {
        "label": "Port of Santos",
        "role": "sa_santos",
        "entityIds": ["santos_port"],
    },
    "transport_sa_paranagua": {
        "label": "Port of Paranaguá",
        "role": "sa_paranagua",
        "entityIds": ["paranagua_port"],
    },
    "transport_eu_rtm": {
        "label": "Port of Rotterdam",
        "role": "eu_rtm",
        "entityIds": ["rotterdam_port"],
    },
    "transport_eu_ham": {
        "label": "Port of Hamburg",
        "role": "eu_ham",
        "entityIds": ["hamburg_port"],
    },
}

EDGES_23: list[tuple[str, str, bool]] = [
    ("bra_farmers", "wholesalers", False),
    ("arg_farmers", "wholesalers", False),
    ("usa_farmers", "wholesalers", False),
    ("wholesalers", "transport_sa_santos", False),
    ("wholesalers", "transport_sa_paranagua", False),
    ("transport_sa_santos", "transport_eu_rtm", True),
    ("transport_sa_paranagua", "transport_eu_ham", True),
    ("arg_farmers", "transport_eu_rtm", True),
    ("usa_farmers", "transport_eu_rtm", True),
    ("transport_eu_rtm", "processors", False),
    ("transport_eu_ham", "processors", False),
    ("processors", "feed_manufacturers", False),
    ("feed_manufacturers", "feed_traders", False),
    ("feed_traders", "eu_farmers", False),
]
