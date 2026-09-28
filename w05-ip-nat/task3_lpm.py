#!/usr/bin/env python3
"""Week 5 · Task 3 — Make longest-prefix match fast.

Textbook §4.3.3.

`LinearTable` is correct and it is what you probably wrote in Task 1: keep the
prefixes in a list, check every one, remember the longest that matched. On six
entries that is fine. A real router holds close to a million, and it has to
answer while the packet is still in the buffer.

Beat it:

    python3 bench.py
    python3 bench.py --yours

Correctness first: `bench.py` checks every one of your answers against the
linear table. A fast router that forwards to the wrong next hop is not a
router, it is an outage.
"""


class LinearTable:
    """Correct, and slow in the obvious way."""

    def __init__(self):
        self.entries = []                     # (prefix_len, network, next_hop)

    def add(self, network, prefix_len, next_hop):
        self.entries.append((prefix_len, network, next_hop))

    def lookup(self, address):
        best = None
        for plen, net, hop in self.entries:
            mask = (0xFFFFFFFF << (32 - plen)) & 0xFFFFFFFF
            if address & mask == net and (best is None or plen > best[0]):
                best = (plen, hop)
        return best[1] if best else None


class YourTable:
    """Prefix-length별 hash table을 이용한 longest-prefix match."""

    def __init__(self):
        # index가 prefix length이고, 값은 {network: next_hop}이다.
        self.tables = [{} for _ in range(33)]

        # prefix마다 mask를 한 번만 계산해서 저장한다.
        self.masks = [
            0 if plen == 0
            else (0xFFFFFFFF << (32 - plen)) & 0xFFFFFFFF
            for plen in range(33)
        ]

        # 실제로 경로가 존재하는 prefix length만 긴 순서로 저장한다.
        self.active_lengths = []

    def add(self, network, prefix_len, next_hop):
        if not 0 <= prefix_len <= 32:
            raise ValueError("prefix length must be between 0 and 32")

        if not 0 <= network <= 0xFFFFFFFF:
            raise ValueError("network must be a 32-bit integer")

        mask = self.masks[prefix_len]

        # network 인수에 host bit가 설정되어 있으면 거부한다.
        if network & mask != network:
            raise ValueError("host bits are set in network")

        bucket = self.tables[prefix_len]

        # 해당 길이의 첫 경로가 들어오면 검색 대상에 추가한다.
        if not bucket:
            self.active_lengths.append(prefix_len)
            self.active_lengths.sort(reverse=True)

        # LinearTable은 동일 길이의 중복 경로가 있을 때 먼저 등록된
        # 경로를 유지하므로 setdefault로 같은 동작을 보장한다.
        bucket.setdefault(network, next_hop)

    def lookup(self, address):
        # 가장 긴 prefix부터 검사한다.
        for prefix_len in self.active_lengths:
            mask = self.masks[prefix_len]
            network = address & mask
            bucket = self.tables[prefix_len]

            if network in bucket:
                return bucket[network]

        return None
