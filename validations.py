from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import quote, unquote, urlsplit, urlunsplit

__all__ = ["validate_website_url", "validate_and_resolve", "UrlValidationError"]

MAX_URL_LENGTH = 2048

_ALLOWED_SCHEMES = ("http", "https")
_DEFAULT_PORTS = {"http": 80, "https": 443}

# RFC 1034/1123 label: 1-63 chars, letters/digits/hyphen, no leading/trailing '-'
_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

# Any C0 control, space, DEL, or Unicode control/format chars anywhere in
# the URL are rejected outright (CVE-2023-24329 mitigation).
_FORBIDDEN_CHARS_RE = re.compile(r"[\x00-\x20\x7f-\x9f]")

# Hostnames that are always refused (plus their subdomains).
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "broadcasthost",
})

# Special-use suffixes: mDNS (.local), common internal TLDs, RFC 8375.
_BLOCKED_SUFFIXES = (".local", ".internal", ".lan", ".home.arpa", ".corp")

# Ports that make no sense for a public "website" and are classic internal
# service targets. Override with blocked_ports=... if your use case differs.
DEFAULT_BLOCKED_PORTS = frozenset({
    0,      # invalid / wildcard
    22,     # SSH
    23,     # Telnet
    25, 465, 587,  # SMTP (SSRF mail relay)
    53,     # DNS
    110, 995,   # POP3
    143, 993,   # IMAP
    389, 636,   # LDAP
    445,    # SMB
    1723,   # PPTP
    3306,   # MySQL
    3389,   # RDP
    5432,   # PostgreSQL
    5984,   # CouchDB
    6379,   # Redis
    8000, 8001, 8081, 8443, 8888,  # common admin panels (optional; drop if you serve such)
    9042,   # Cassandra
    9200, 9300,   # Elasticsearch
    11211,  # Memcached
    27017, 27018,  # MongoDB
    50070,  # Hadoop
})

# Every IPv4/IPv6 block that is not a public unicast destination.
# IPv4-mapped IPv6 addresses are converted to IPv4 before this check.
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        # IPv4
        "0.0.0.0/8",          # "this network" (0.0.0.0/0.0.0.0)
        "10.0.0.0/8",         # RFC 1918 private
        "100.64.0.0/10",      # RFC 6598 CGNAT
        "127.0.0.0/8",        # loopback
        "169.254.0.0/16",     # link-local (AWS/GCP/Azure metadata 169.254.169.254)
        "172.16.0.0/12",      # RFC 1918 private
        "192.0.0.0/24",       # IETF protocol assignments
        "192.0.2.0/24",       # TEST-NET-1 documentation
        "192.88.99.0/24",     # 6to4 relay anycast (deprecated)
        "192.168.0.0/16",     # RFC 1918 private
        "198.18.0.0/15",      # benchmarking
        "198.51.100.0/24",    # TEST-NET-2 documentation
        "203.0.113.0/24",     # TEST-NET-3 documentation
        "224.0.0.0/4",        # multicast
        "240.0.0.0/4",        # reserved (future use / broadcast)
        # IPv6
        "::/128",             # unspecified
        "::1/128",            # loopback
        "fc00::/7",           # RFC 4193 ULA (covers AWS fd00:ec2::254 metadata)
        "fe80::/10",          # link-local
        "ff00::/8",           # multicast
        "2001:db8::/32",      # documentation
    )
)

_IDNA_CODEC = "idna"


class UrlValidationError(ValueError):
    """Raised by validate_and_resolve when a URL is rejected."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if ip is not a public unicast destination.

    IPv4-mapped/compatible IPv6 (e.g. ::ffff:127.0.0.1) is checked as IPv4.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            ip = mapped
    return any(ip in net for net in _BLOCKED_NETWORKS)


def _parse_ipv4_notation(host: str) -> ipaddress.IPv4Address | None:
    """Parse an IPv4 address in ANY notation, or return None.

    Covers dotted decimal plus the alternative notations attackers use to
    evade string blacklists (PortSwigger SSRF guide): pure decimal
    ("2130706433" == 127.0.0.1), octal ("017700000001"), hex ("0x7f000001"),
    and the short form ("127.1" == 127.0.0.1).
    """
    h = host
    base = 10
    if h.lower().startswith("0x"):
        base = 16
        h = h[2:]
    elif len(h) > 1 and h.startswith("0") and h.isdigit():
        base = 8

    if "." in h:
        parts = h.split(".")
        if not 1 <= len(parts) <= 4:
            return None
        value = 0
        for part in parts:
            if not part or len(part) > 3:
                return None
            try:
                n = int(part, base)
            except ValueError:
                return None
            if not 0 <= n <= 255:
                return None
            value = (value << 8) | n
        # right-pad short forms ("127.1" -> 127.0.0.1)
        value <<= 8 * (4 - len(parts))
        try:
            return ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            return None

    if not h:
        return None
    try:
        return ipaddress.IPv4Address(int(h, base))  # "2130706433", "017700000001", "0x7f000001"
    except ValueError:
        return None


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the IP for host if it is an IP literal in any notation, else None."""
    # IPv6 literal (urlsplit already stripped the brackets).
    if ":" in host:
        try:
            return ipaddress.ip_address(host)
        except ValueError:
            return None
    # Plain IPv4 in standard or alternative notation.
    if host and all(c in "0123456789.xabcdefABCDEF" for c in host) and any(
        c.isdigit() for c in host
    ):
        v4 = _parse_ipv4_notation(host)
        if v4 is not None:
            return v4
        # fall through: might be a weird-but-valid DNS name like "123.abc"
    return None


def _normalize_hostname(host: str) -> str | None:
    """Validate + normalize a hostname; return ASCII/punycode form or None."""
    if not host or len(host) > 253:
        return None

    host = host.rstrip(".").lower()
    if not host:
        return None

    labels = host.split(".")
    ascii_labels = []
    for label in labels:
        if not label:
            return None  # empty label ("example..com")
        try:
            label = label.encode(_IDNA_CODEC).decode("ascii").lower()
        except (UnicodeError, ValueError):
            return None  # invalid IDNA/punycode
        if not _LABEL_RE.match(label):
            return None  # underscores, bad hyphens, over-length labels
        ascii_labels.append(label)

    return ".".join(ascii_labels)


def _is_blocked_hostname(host: str) -> bool:
    if host in _BLOCKED_HOSTNAMES:
        return True
    return any(host.endswith(sfx) for sfx in _BLOCKED_SUFFIXES)


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    # unquote+requote canonicalizes mixed/invalid escapes without changing
    # the meaning of valid ones.
    return quote(unquote(path), safe="/%:@!$&'()*+,;=-._~")


def _normalize_query(query: str) -> str:
    return quote(unquote(query), safe="=&;%:@!$'()*+,/?-._~")


def validate_website_url(
    value,
    *,
    blocked_ports: frozenset[int] | set[int] | None = DEFAULT_BLOCKED_PORTS,
    allow_ip_hosts: bool = True,
    require_dot: bool = False,
):
    """Validate and normalize a website URL.

    Returns:
        Normalized URL string (canonical form — fetch THIS, never the raw
        input), or None if invalid / disallowed.

    Args:
        blocked_ports: ports to refuse. Pass an empty set to allow any port.
        allow_ip_hosts: whether a bare IP literal host is acceptable.
        require_dot: require at least one dot in the hostname (no intranet
                     single-label names like "http://intranet").
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip()
    if not value or len(value) > MAX_URL_LENGTH:
        return None

    # Blank/control characters anywhere (CVE-2023-24329) — before parsing.
    if _FORBIDDEN_CHARS_RE.search(value):
        return None

    # Add https:// when the user enters e.g. "example.com".
    if "://" not in value:
        value = f"https://{value}"

    try:
        parsed = urlsplit(value)
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        return None

    # A usable authority is mandatory ("https:example.com" is not a website).
    if not parsed.netloc or parsed.hostname is None:
        return None

    # Explicit bracket audit — hardening for CVE-2025-0938 on interpreters
    # where urlsplit accepts stray '[' / ']' in the authority.
    if ("[" in parsed.netloc or "]" in parsed.netloc) and not (
        parsed.netloc.startswith("[") and "]" in parsed.netloc
    ):
        return None

    # Reject credentials: https://user:password@example.com
    # (also catches the user@:port@host and user%40host tricks)
    if parsed.username is not None or parsed.password is not None:
        return None

    # Reject backslashes in the authority (WHATWG parsers treat them as '/',
    # Python doesn't — a classic parser-differential SSRF vector).
    if "\\" in parsed.netloc:
        return None

    # Port
    try:
        port = parsed.port
    except ValueError:
        return None  # non-numeric / out-of-range port
    if port is not None:
        if not 1 <= port <= 65535:
            return None
        if blocked_ports and port in blocked_ports:
            return None

    # Hostname
    hostname = parsed.hostname.lower()

    # IP literal first: IPv6 addresses contain ':' and must not go through
    # RFC-1034 hostname label validation.
    ip = _parse_ip_literal(hostname)
    if ip is not None:
        if not allow_ip_hosts or _is_blocked_ip(ip):
            return None
        host_out = str(ip)
    else:
        host_norm = _normalize_hostname(hostname)
        if host_norm is None:
            return None
        if require_dot and "." not in host_norm:
            return None
        if _is_blocked_hostname(host_norm):
            return None
        host_out = host_norm

    # Rebuild a clean normalized URL.
    netloc = host_out if ":" not in host_out else f"[{host_out}]"
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"

    normalized = urlunsplit((
        scheme,
        netloc,
        _normalize_path(parsed.path),
        _normalize_query(parsed.query),
        "",  # fragment dropped
    ))
    return normalized


def validate_and_resolve(
    value,
    *,
    blocked_ports: frozenset[int] | set[int] | None = DEFAULT_BLOCKED_PORTS,
    allow_ip_hosts: bool = True,
    require_dot: bool = False,
    dns_timeout: float = 3.0,
):
    """Like validate_website_url, but also resolves the hostname via DNS and
    rejects it if ANY resolved address is non-public.

    This closes the "attacker-controlled domain pointing at 127.0.0.1"
    hole that pure string validation cannot see. It does NOT remove the
    need to re-validate / pin the IP at fetch time: DNS answers can change
    between this check and the actual connection (rebinding), so the fetcher
    should connect to the IP validated here and send Host/SNI accordingly.
    """
    url = validate_website_url(
        value,
        blocked_ports=blocked_ports,
        allow_ip_hosts=allow_ip_hosts,
        require_dot=require_dot,
    )
    if url is None:
        raise UrlValidationError("URL rejected by validator")

    host = urlsplit(url).hostname
    ip = _parse_ip_literal(host)
    if ip is not None:
        return url  # literal host already checked

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(dns_timeout)
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise UrlValidationError(f"hostname does not resolve: {exc}") from exc
    finally:
        socket.setdefaulttimeout(old_timeout)

    if not infos:
        raise UrlValidationError("hostname resolves to no addresses")

    resolved = {ipaddress.ip_address(info[4][0]) for info in infos}
    blocked = [ip for ip in resolved if _is_blocked_ip(ip)]
    if blocked:
        raise UrlValidationError(
            f"hostname resolves to non-public address(es): "
            f"{', '.join(str(b) for b in blocked)}"
        )
    return url
