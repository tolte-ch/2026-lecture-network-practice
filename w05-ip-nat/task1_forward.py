#!/usr/bin/env python3
"""Week 5 · Task 1 — Subnets and longest-prefix match.

Textbook §4.3.2 (IPv4 addressing, CIDR) and §4.3.3 (forwarding).

Two things a router does with every packet: work out which prefixes the
destination falls inside, and pick the longest one. The second is the whole
of "longest prefix match", and it is the reason the internet's routing table
can hold a million entries and still be answerable.

You build both, from integers up. No `ipaddress` module - that library is
exactly the thing you are supposed to understand this week.

    python3 task1_forward.py --verify
"""
import argparse

def ip_to_int(address):
    parts = address.split(".")
    if len(parts) != 4:
        raise ValueError(f"invalid IPv4 address: {address}")

    octets = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"invalid IPv4 address: {address}")
        value = int(part)
        if not 0 <= value <= 255:
            raise ValueError(f"invalid IPv4 address: {address}")
        octets.append(value)

    result = 0
    for octet in octets:
        result = (result << 8) | octet
    return result


def int_to_ip(value):
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("IPv4 integer is out of range")

    return ".".join(str((value >> shift) & 0xFF)
                    for shift in (24, 16, 8, 0))


def prefix_mask(prefix_len):
    if prefix_len == 0:
        return 0
    return (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF


def parse_cidr(cidr):
    try:
        address, prefix_text = cidr.split("/")
    except ValueError:
        raise ValueError(f"invalid CIDR: {cidr}")

    try:
        prefix_len = int(prefix_text)
    except ValueError:
        raise ValueError(f"invalid prefix length: {prefix_text}")

    if not 0 <= prefix_len <= 32:
        raise ValueError("prefix length must be between 0 and 32")

    address_int = ip_to_int(address)
    mask = prefix_mask(prefix_len)
    host_mask = 0xFFFFFFFF ^ mask

    if address_int & host_mask:
        raise ValueError(f"host bits are set: {cidr}")

    return address_int, prefix_len


def network_range(cidr):
    network, prefix_len = parse_cidr(cidr)
    mask = prefix_mask(prefix_len)
    host_mask = 0xFFFFFFFF ^ mask
    broadcast = network | host_mask

    if prefix_len <= 30:
        first = network + 1
        last = broadcast - 1
    elif prefix_len == 31:
        # RFC 3021: point-to-point 링크에서는 두 주소 모두 사용 가능
        first = network
        last = broadcast
    else:  # /32
        # 하나의 호스트만 나타내는 host route
        first = network
        last = network

    return int_to_ip(first), int_to_ip(last), int_to_ip(broadcast)

class ForwardingTable:
    def __init__(self):
        self.entries = []

    def add(self, cidr, next_hop):
        network, prefix_len = parse_cidr(cidr)
        mask = prefix_mask(prefix_len)

        for saved_network, saved_prefix, _, _ in self.entries:
            if saved_network == network and saved_prefix == prefix_len:
                raise ValueError(f"duplicate route: {cidr}")

        self.entries.append((network, prefix_len, mask, next_hop))

    def lookup(self, address):
        address_int = ip_to_int(address)

        best_prefix = -1
        best_next_hop = None

        for network, prefix_len, mask, next_hop in self.entries:
            if (address_int & mask) == network:
                if prefix_len > best_prefix:
                    best_prefix = prefix_len
                    best_next_hop = next_hop

        return best_next_hop

# ------------------------------------------------------------------- harness
RANGE_CASES = [
    ("192.168.0.0/24",  "192.168.0.1",   "192.168.0.254",  "192.168.0.255"),
    ("10.0.0.0/8",      "10.0.0.1",      "10.255.255.254", "10.255.255.255"),
    ("172.16.32.0/20",  "172.16.32.1",   "172.16.47.254",  "172.16.47.255"),
    ("203.0.113.64/26", "203.0.113.65",  "203.0.113.126",  "203.0.113.127"),
]

TABLE = [
    ("0.0.0.0/0",       "default-gw"),
    ("10.0.0.0/8",      "campus"),
    ("10.20.0.0/16",    "eng-building"),
    ("10.20.30.0/24",   "lab-floor"),
    ("10.20.30.64/26",  "lab-rack-2"),
    ("192.168.1.0/24",  "home"),
]

LOOKUP_CASES = [
    ("10.20.30.70",   "lab-rack-2"),     # inside all four 10.x entries
    ("10.20.30.10",   "lab-floor"),
    ("10.20.99.1",    "eng-building"),
    ("10.99.0.1",     "campus"),
    ("8.8.8.8",       "default-gw"),
    ("192.168.1.77",  "home"),
]


def verify():
    fails = 0
    for cidr, first, last, bcast in RANGE_CASES:
        try:
            got = network_range(cidr)
        except NotImplementedError:
            print("  network_range is still a stub"); return 1
        except Exception as e:
            print(f"  FAIL  {cidr:<18} raised {e!r}"); fails += 1; continue
        ok = tuple(got) == (first, last, bcast)
        print(f"  {'ok  ' if ok else 'FAIL'}  {cidr:<18} {got}")
        fails += not ok

    t = ForwardingTable()
    try:
        for cidr, hop in TABLE:
            t.add(cidr, hop)
    except NotImplementedError:
        print("  ForwardingTable is still a stub"); return 1

    for addr, expect in LOOKUP_CASES:
        got = t.lookup(addr)
        ok = got == expect
        print(f"  {'ok  ' if ok else 'FAIL'}  {addr:<16} -> {got}  (want {expect})")
        fails += not ok

    print(f"\n  {len(RANGE_CASES) + len(LOOKUP_CASES) - fails}"
          f"/{len(RANGE_CASES) + len(LOOKUP_CASES)} ok")
    return 1 if fails else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    raise SystemExit(verify() if a.verify else p.print_help())
