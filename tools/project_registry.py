"""Project-aware service normalization for the knowledge/decision toolchain.

Centralizes the (prefix, service-map) knowledge that was previously hardcoded
per-tool, so adding a new project (e.g. sock-shop) touches ONE place instead
of four. Also normalizes service names so knowledge rules match across
plural/singular spellings (carts -> CART, orders -> ORDER).
"""

from __future__ import annotations

# Project prefix -> canonical namespace + how to normalize the service token.
# Add a new project here (one place) and the gate / decision_engine /
# knowledge_updater all pick it up.
PROJECTS: dict[str, dict[str, object]] = {
    "OB": {"namespace": "online-boutique-lab", "service_alias": {"PAYMENTSERVICE": "PAYMENT", "PRODUCTCATALOGSERVICE": "PRODUCTCATALOG", "CURRENCYSERVICE": "CURRENCY", "CHECKOUTSERVICE": "CHECKOUT", "SHIPPINGSERVICE": "SHIPPING", "CARTSERVICE": "CART", "EMAILSERVICE": "EMAIL", "ADSERVICE": "AD", "RECOMMENDATIONSERVICE": "RECOMMENDATION"}},
    "OTEL": {"namespace": "otel-demo-lab", "service_alias": {"PRODUCT-CATALOG": "PRODUCTCATALOG"}},
    "TT": {"namespace": "train-ticket-lab", "service_alias": {"TS-PAYMENT-SERVICE": "PAYMENT", "TS-ORDER-SERVICE": "ORDER", "TS-STATION-SERVICE": "STATION", "TS-BASIC-SERVICE": "BASIC", "TS-CART-SERVICE": "CART"}},
    "SOCK": {"namespace": "sock-shop-lab", "service_alias": {"CART": "CART", "CARTS": "CART", "CATALOGUE": "CATALOGUE", "CATALOG": "CATALOGUE", "ORDERS": "ORDER", "ORDER": "ORDER", "PAYMENT": "PAYMENT", "SHIPPING": "SHIPPING", "USER": "USER", "QUEUE-MASTER": "QUEUE-MASTER"}},
}

# Generic plural->singular for services not in the alias map.
PLURAL_ALIAS = {
    "CARTS": "CART", "ORDERS": "ORDER", "CATEGORIES": "CATEGORY",
    "ITEMS": "ITEM", "PRODUCTS": "PRODUCT", "USERS": "USER",
}


def project_of(candidate_id: str, strict: bool = False) -> str:
    """Resolve the project prefix for a candidate id.

    Phase-4 remediation (findings #13): an unknown prefix previously fell back
    silently to TT, which could misroute candidates from a new project into the
    train-ticket knowledge/evidence universe. With strict=True the caller
    explicitly opts into fail-closed behavior (ValueError on unknown prefix);
    default remains the legacy tolerant lookup so existing tools keep working
    unless they opt in. Decision/summary tools should pass strict=True.
    """
    upper = candidate_id.upper()
    for prefix in PROJECTS:
        if upper.startswith(f"{prefix}-"):
            return prefix
    if strict:
        raise ValueError(
            f"unknown project prefix in candidate id {candidate_id!r}; "
            f"known prefixes: {sorted(PROJECTS)}"
        )
    return "TT"  # legacy tolerant fallback (flagged; callers should use strict=True)


def normalize_service(candidate_id: str, strict: bool = False) -> str:
    """Strip project prefix + fault suffix, normalize case and plural.

    SOCK-CARTS-LOSS-100 -> CART; OB-CHECKOUT-DELAY-2000 -> CHECKOUT;
    OTEL-PRODUCTCATALOG-DELAY-2000 -> PRODUCTCATALOG; TT-BASIC-DELAY-100 -> BASIC.
    strict=True propagates to project_of so unknown projects fail closed.
    """
    upper = candidate_id.upper()
    project = project_of(upper, strict=strict)
    rest = upper[len(project) + 1:] if upper.startswith(f"{project}-") else upper
    # strip fault suffix
    for token in ("-DELAY", "-LOSS", "-KILL", "-CPU", "-RESTART", "-STRESS"):
        rest = rest.split(token)[0]
    alias = PROJECTS[project]["service_alias"]
    if rest in alias:
        return alias[rest]
    if rest in PLURAL_ALIAS:
        return PLURAL_ALIAS[rest]
    return rest


def fault_of(candidate_id: str) -> str:
    upper = candidate_id.upper()
    if "LOSS" in upper:
        return "loss"
    if "KILL" in upper:
        return "kill"
    if "DELAY" in upper:
        return "delay"
    if "CPU" in upper:
        return "cpu"
    return "unknown"
