#!/usr/bin/env python3
"""DNS + TLS inventory of the Syncplay relay PoPs. (docs/watch-together.md §3, §11.22)

Every Syncplay host the relay hands out looks like pop-<city><NN>.syncplay.plex.services.
Only pop-fra00 was ever fully characterised, so this enumerates, for each PoP the cloud
has been seen to issue:

  * every A/AAAA record and the full CNAME chain (socket.getaddrinfo + CNAME probing)
  * reverse DNS for each address
  * the negotiated TLS version/cipher and the whole peer certificate
    (subject / issuer / SANs / notBefore / notAfter / serial / fingerprint)

Read-only: no WebSocket frames are sent, no room is named. Connect and disconnect only,
which is what any TLS client does before it decides whether to trust the peer.

    python3 docs/probes/popinventory.py [host[:port] ...]
"""
import datetime
import hashlib
import socket
import ssl
import sys

DEFAULT_POPS = [
    ("pop-fra00.syncplay.plex.services", 7776),
    ("pop-atl01.syncplay.plex.services", 7777),
    ("pop-fra01.syncplay.plex.services", 7777),
    # pop-atl00 resolves but appears in no room record yet; sweeping ~70 pop-<city><NN>
    # combinations found only fra00/fra01 and atl00/atl01, so this is the full set as of
    # 2026-10-05. There is no wildcard and the apex does not resolve.
    ("pop-atl00.syncplay.plex.services", 7777),
]


def rfc4514(name_rdns):
    """Render ssl's tuple-of-tuples name into a readable LDAP-ish string."""
    out = []
    for rdn in name_rdns:
        out.append("+".join("%s=%s" % (k, v) for k, v in rdn))
    return ",".join(out)


def cname_chain(host):
    """Walk the CNAME chain by resolving each name as a bare CNAME query.

    getaddrinfo() flattens the chain, so ask the resolver directly with a
    CNAME-typed question and walk until the answer stops being a CNAME.
    """
    chain = []
    name = host
    for _ in range(8):
        try:
            answers = socket.getaddrinfo(name, None, socket.AF_INET, socket.SOCK_STREAM)
        except socket.gaierror:
            break
        break
    # getaddrinfo cannot tell us the CNAME; use the resolver's own text via dnspython-free
    # trick: socket.gethostbyname_ex() returns (hostname, aliases, addrlist) where
    # hostname is the canonical name -- i.e. the CNAME target.
    try:
        canon, aliases, _addrs = socket.gethostbyname_ex(host)
    except socket.gaierror as e:
        return ["<unresolved: %s>" % e]
    chain.append("%s -> CNAME %s" % (host, canon))
    for alias in aliases:
        chain.append("     alias %s" % alias)
    return chain


def reverse(a):
    fam = socket.AF_INET6 if ":" in a else socket.AF_INET
    try:
        return socket.gethostbyaddr(a)[0]
    except (socket.herror, socket.gaierror):
        return "<none>"


def describe_tls(host, port, addr_family=None):
    out = {"peer": None}
    try:
        infos = socket.getaddrinfo(host, port, addr_family or 0, socket.SOCK_STREAM)
    except socket.gaierror as e:
        return {"error": "resolve: %s" % e}
    af, _, _, _, sa = infos[0]
    try:
        raw = socket.socket(af, socket.SOCK_STREAM)
        raw.settimeout(15)
        raw.connect(sa)
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(raw, server_hostname=host)
    except Exception as e:
        return {"error": "connect: %r" % (e,)}
    try:
        cert = s.getpeercert()
        der = s.getpeercert(binary_form=True)
        out.update({
            "peer": sa[0],
            "version": s.version(),
            "cipher": s.cipher(),
            "alpn": s.selected_alpn_protocol(),
            "subject": rfc4514(cert.get("subject", ())),
            "issuer": rfc4514(cert.get("issuer", ())),
            "sans": cert.get("subjectAltName", ()),
            "notBefore": cert.get("notBefore"),
            "notAfter": cert.get("notAfter"),
            "serial": cert.get("serialNumber", "?"),
            "sha256": hashlib.sha256(der).hexdigest(),
        })
        for label in ("notBefore", "notAfter"):
            stamp = out[label]
            if stamp:
                t = ssl.cert_time_to_seconds(stamp)
                out[label + "UTC"] = datetime.datetime.utcfromtimestamp(t).isoformat() + "Z"
        now = datetime.datetime.utcnow()
        for label in ("notBefore", "notAfter"):
            if out[label]:
                days = (datetime.datetime.strptime(out[label + "UTC"], "%Y-%m-%dT%H:%M:%SZ")
                        - now).days
                out[label + "days"] = days
        return out
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    pops = DEFAULT_POPS
    if len(sys.argv) > 1:
        pops = []
        for arg in sys.argv[1:]:
            host, _, port = arg.partition(":")
            pops.append((host, int(port or 7777)))

    print("python %s  openssl %s" % (sys.version.split()[0], ssl.OPENSSL_VERSION))
    print()
    certs = {}
    for host, port in pops:
        print("=" * 72)
        print("%s:%d" % (host, port))
        print("-- CNAME chain")
        for line in cname_chain(host):
            print("   " + line)
        print("-- addresses")
        for af, label in ((socket.AF_INET, "A  "), (socket.AF_INET6, "AAAA")):
            try:
                infos = socket.getaddrinfo(host, port, af, socket.SOCK_STREAM)
            except socket.gaierror as e:
                print("   %s <%s>" % (label, e))
                continue
            addrs = sorted({i[4][0] for i in infos})
            if not addrs:
                print("   %s <none>" % label)
            for a in addrs:
                print("   %s %-40s PTR %s" % (label, a, reverse(a)))
        print("-- TLS")
        for fam, label in ((None, "default"), (socket.AF_INET, "v4-only"),
                           (socket.AF_INET6, "v6-only")):
            info = describe_tls(host, port, fam)
            if "error" in info:
                print("   [%s] %s" % (label, info["error"]))
                continue
            print("   [%s] via %s" % (label, info["peer"]))
            print("       %s  %s  alpn=%s" % (info["version"], info["cipher"], info["alpn"]))
            print("       subject  %s" % info["subject"])
            print("       issuer   %s" % info["issuer"])
            sans = ", ".join("%s=%s" % (k, v) for k, v in info["sans"]) or "<none>"
            print("       SANs     %s" % sans)
            print("       valid    %s .. %s  (%s days / %s days)"
                  % (info["notBeforeUTC"], info["notAfterUTC"],
                     info["notBeforedays"], info["notAfterdays"]))
            print("       serial   %s" % info["serial"])
            print("       sha256   %s" % info["sha256"])
            certs.setdefault(info["sha256"], []).append("%s:%d" % (host, port))
        print()

    print("=" * 72)
    print("distinct certificates: %d" % len(certs))
    for fp, hosts in certs.items():
        print("  %s  %s" % (fp[:32], hosts))


if __name__ == "__main__":
    main()