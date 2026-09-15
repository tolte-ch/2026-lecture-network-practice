#!/usr/bin/env python3
"""Week 3 · Task 1 — Build your own iterative resolver.

Textbook §2.4.2 - §2.4.3.

`dig +trace` walks root -> TLD -> authoritative for you. In this task you do
that walk yourself: start at a root server, read the delegation it returns,
ask the next server, and keep going until somebody answers authoritatively.

You may shell out to `dig` for the transport, or use a DNS library
(`dnspython` is in the container). Either is fine - what matters is that
*you* follow the delegations rather than letting a tool do it.

    python3 task1_resolve.py www.korea.ac.kr
    python3 task1_resolve.py --verify        # check yourself against dig

Pass condition
--------------
`--verify` resolves five names with your resolver and with `dig`, and the
addresses must agree. A name behind a CDN may legitimately return a different
address each time; the harness compares the *set of authoritative nameservers*
you ended at for those, not the address.
"""

import argparse
import subprocess
import sys

import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.query
import dns.rcode
import dns.rdatatype

# Root servers. Everything starts here; there is no earlier step.
ROOT_SERVERS = [
    "198.41.0.4",       # a.root-servers.net
    "199.9.14.201",     # b.root-servers.net
    "192.33.4.12",      # c.root-servers.net
]

# (name, kind).  "stable" names must match dig exactly.  "cdn" names are served
# from many replicas and may legitimately give you a different address than dig
# got a second earlier - for those we only require that you reached an answer.
VERIFY_NAMES = [
    ("www.korea.ac.kr", "stable"),
    ("dns.google", "stable"),
    ("en.wikipedia.org", "stable"),
    ("www.stanford.edu", "stable"),
    ("www.microsoft.com", "cdn"),
]


class Resolver:
    """A small iterative DNS resolver."""

    TIMEOUT = 2.0
    MAX_DEPTH = 20

    def resolve(self, name):
        normalized = dns.name.from_text(name).to_text().lower()
        path = []

        # 이번 resolve 호출 안에서 알아낸 주소를 재사용
        self._address_cache = {}

        address = self._walk(
            name=normalized,
            path=path,
            depth=0,
            active_names=set(),
        )
        return address, path

    def _make_query(self, name):
        """Create a non-recursive A query."""
        query = dns.message.make_query(name, dns.rdatatype.A)

        # make_query() normally sets RD (Recursion Desired).
        # This assignment requires us to follow delegations ourselves.
        query.flags &= ~dns.flags.RD

        return query

    def _ask_servers(self, name, servers, path):
        """Ask servers in order until one returns a usable response."""
        query = self._make_query(name)
        last_error = None

        for server in servers:
            path.append(server)

            try:
                response = dns.query.udp(
                    query,
                    server,
                    timeout=self.TIMEOUT,
                )

                # If the UDP response was truncated, retry the same query via TCP.
                if response.flags & dns.flags.TC:
                    response = dns.query.tcp(
                        query,
                        server,
                        timeout=self.TIMEOUT,
                    )

            except (dns.exception.DNSException, OSError) as exc:
                # This server did not answer correctly. Try the next NS.
                last_error = exc
                continue

            rcode = response.rcode()

            if rcode in (dns.rcode.NOERROR, dns.rcode.NXDOMAIN):
                return response

            # SERVFAIL, REFUSED, and similar errors should not prevent us
            # from trying another authoritative server.
            last_error = RuntimeError(
                f"{server} returned {dns.rcode.to_text(rcode)}"
            )

        raise RuntimeError(
            f"no DNS server answered for {name}"
        ) from last_error

    def _walk(self, name, path, depth, active_names):
        """Walk root -> TLD -> authoritative servers."""
        if depth >= self.MAX_DEPTH:
            raise RuntimeError(
                f"maximum DNS lookup depth exceeded while resolving {name}"
            )

        name = dns.name.from_text(name).to_text().lower()

        if name in self._address_cache:
            return self._address_cache[name]

        # Detect CNAME and missing-glue resolution cycles.
        if name in active_names:
            raise RuntimeError(f"DNS lookup loop detected at {name}")

        active_names.add(name)

        try:
            current_servers = list(ROOT_SERVERS)

            # This limit catches malformed referral loops even when the
            # queried domain name itself does not change.
            for _ in range(self.MAX_DEPTH):
                response = self._ask_servers(
                    name,
                    current_servers,
                    path,
                )

                if response.rcode() == dns.rcode.NXDOMAIN:
                    raise RuntimeError(f"{name} does not exist")

                cname_target = None

                # First inspect the Answer section.
                for rrset in response.answer:
                    if rrset.rdtype == dns.rdatatype.A:
                        # An A rrset can contain multiple addresses.
                        # The provided interface asks for one address.
                        address = next(iter(rrset)).address
                        self._address_cache[name] = address
                        return address

                    if rrset.rdtype == dns.rdatatype.CNAME:
                        cname_target = next(iter(rrset)).target.to_text()

                if cname_target is not None:
                    # A new name can belong to a completely different DNS
                    # hierarchy, so restart from the root.
                    address = self._walk(
                        cname_target,
                        path,
                        depth + 1,
                        active_names,
                    )
                    self._address_cache[name] = address
                    return address

                # No final answer: inspect the Authority section for a
                # delegation to the next zone.
                ns_names = []

                for rrset in response.authority:
                    if rrset.rdtype == dns.rdatatype.NS:
                        for record in rrset:
                            ns_names.append(
                                record.target.to_text().lower()
                            )

                if not ns_names:
                    raise RuntimeError(
                        f"{name}: response contained neither "
                        "an A/CNAME answer nor an NS delegation"
                    )

                # Collect glue A records from the Additional section.
                glue = {}

                for rrset in response.additional:
                    if rrset.rdtype != dns.rdatatype.A:
                        continue

                    owner = rrset.name.to_text().lower()
                    glue.setdefault(owner, [])

                    for record in rrset:
                        glue[owner].append(record.address)

                next_servers = []
                missing_glue = []

                for ns_name in ns_names:
                    if ns_name in glue:
                        next_servers.extend(glue[ns_name])
                    else:
                        missing_glue.append(ns_name)

# Glue 주소가 있으면 우선 그것만 사용한다.
                # Glue가 전혀 없을 때는 최대 2개 NS 주소만 해석한다.
                if not next_servers:
                    for ns_name in missing_glue:
                        try:
                            ns_address = self._walk(
                                ns_name,
                                path,
                                depth + 1,
                                active_names,
                            )
                            next_servers.append(ns_address)

                            # 장애 대비용으로 최대 2개 주소를 확보한다.
                            if len(next_servers) >= 2:
                                break

                        except RuntimeError:
                            continue

                # Remove duplicate addresses while retaining their order.
                current_servers = list(dict.fromkeys(next_servers))

                if not current_servers:
                    raise RuntimeError(
                        f"{name}: could not obtain an address for "
                        "any delegated nameserver"
                    )

        finally:
            active_names.remove(name)

# ------------------------------------------------------------------- harness
def dig_answer(name):
    """What the system resolver says, for comparison."""
    out = subprocess.run(["dig", "+short", name, "A"],
                         capture_output=True, text=True).stdout
    return [l for l in out.split() if l and l[0].isdigit()]


def verify():
    r, failures = Resolver(), 0
    for name, kind in VERIFY_NAMES:
        try:
            addr, path = r.resolve(name)
        except NotImplementedError:
            print("Nothing implemented yet - write Resolver.resolve first.")
            return 1
        except Exception as e:
            print(f"  FAIL  {name:<22} your resolver raised {e!r}")
            failures += 1
            continue
        expected = dig_answer(name)
        if addr in expected:
            note = ""
        elif kind == "cdn":
            note = "  <- differs, but this name is CDN-hosted. Explain it."
        else:
            note = "  <- should have matched"
            failures += 1
        print(f"  {'FAIL' if note.endswith('matched') else 'ok  '}  {name:<22} "
              f"you={addr:<16} dig={','.join(expected) or '-'}   "
              f"hops={len(path)}{note}")
    print(f"\n  {len(VERIFY_NAMES) - failures}/{len(VERIFY_NAMES)} ok")
    return 1 if failures else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", nargs="?", default="www.korea.ac.kr")
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()

    if a.verify:
        sys.exit(verify())

    addr, path = Resolver().resolve(a.name)
    for i, server in enumerate(path, 1):
        print(f"  {i}. asked {server}")
    print(f"\n  {a.name} -> {addr}")


if __name__ == "__main__":
    main()
