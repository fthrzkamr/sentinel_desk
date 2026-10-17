"""Lightweight, offline URL-suspicion heuristics — no WHOIS/external API calls,
so this has zero rate-limit, cost, or network-dependency concerns and can run
inline on every synced browsing-history entry. Not a real ML model: a small
set of structural red flags long used by phishing-detection heuristics
(raw-IP host, punycode, excessive subdomains, brand-name typosquatting).
False positives are expected and acceptable — this feeds a WARNING/CRITICAL
alert an admin reviews, not an automatic block."""

import re
from urllib.parse import urlparse

_IP_HOST_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# Small, extend-as-needed list of brand names commonly impersonated in
# phishing kits, paired with their real registrable domain(s). Only brands
# actually relevant to an Indonesian company's employees are worth including
# here — add more as real incidents surface.
_BRAND_DOMAINS = {
    "paypal": ["paypal.com"],
    "microsoft": ["microsoft.com", "live.com", "office.com"],
    "google": ["google.com", "gmail.com"],
    "apple": ["apple.com", "icloud.com"],
    "bankbca": ["bca.co.id", "klikbca.com"],
    "bri": ["bri.co.id"],
    # bankmandiri.co.id is the retail site; koprabymandiri.com is Bank
    # Mandiri's own separate, official wholesale/corporate banking
    # platform ("Kopra by Mandiri") - a real product with its own
    # registrable domain, not a lookalike. Verified against Bank Mandiri's
    # own site, which names koprabymandiri.com as the official address.
    "mandiri": ["bankmandiri.co.id", "koprabymandiri.com"],
    "bni": ["bni.co.id"],
}

_SUSPICIOUS_KEYWORDS = ["login", "verify", "secure", "confirm", "update-account", "signin"]


def _registrable_domain(hostname: str) -> str:
    """Best-effort last-two-labels extraction (e.g. "a.b.example.co.id" isn't
    handled perfectly without a public-suffix list, but "example.com" out of
    "sub.example.com" is — good enough for a heuristic, not a definitive
    domain-ownership check."""
    parts = hostname.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else hostname


def classify_url(url: str) -> list[str]:
    """Returns a list of matched suspicion reasons — empty means not flagged."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
    except ValueError:
        return []

    if not hostname:
        return []

    reasons = []

    if _IP_HOST_RE.match(hostname):
        reasons.append("host adalah alamat IP mentah")

    if "xn--" in hostname:
        reasons.append("domain punycode/homograph")

    if hostname.count(".") > 3:
        reasons.append("subdomain berlapis berlebihan")

    registrable = _registrable_domain(hostname)
    for brand, real_domains in _BRAND_DOMAINS.items():
        if brand in hostname and registrable not in real_domains:
            reasons.append(f"meniru domain '{brand}' tapi bukan domain resminya")
            break

    if any(keyword in hostname for keyword in _SUSPICIOUS_KEYWORDS) and not any(
        registrable in domains for domains in _BRAND_DOMAINS.values()
    ):
        reasons.append("kata kunci mencurigakan pada domain tidak dikenal")

    return reasons
