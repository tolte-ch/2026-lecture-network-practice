#!/usr/bin/env python3
"""Week 7 · Task 3 — A switch that runs out of room.

Textbook §6.4.3.

A switch does not have room for every station on the network. Its forwarding
table sits in a fixed amount of fast memory, and when that fills, something has
to go. Whatever goes gets **flooded** the next time anyone sends to it - out of
every port, to every station that did not ask for it.

`NaiveSwitch` handles a full table the simplest way: throw out whichever entry
has been there longest. That is a perfectly reasonable first idea and it is
close to the worst thing you can do with this traffic.

    python3 bench.py
    python3 bench.py --yours

Correctness first: every frame whose destination is reachable must still reach
it. A switch that floods less because it delivers less is not a switch.
"""
from collections import OrderedDict


class NaiveSwitch:
    """Correct. Evicts the oldest entry, which is not the least useful one."""

    BROADCAST = "ff:ff:ff:ff:ff:ff"

    def __init__(self, ports, capacity):
        self.ports = ports
        self.capacity = capacity
        self.table = OrderedDict()                 # mac -> port, insertion order

    def handle(self, frame, in_port):
        src, dst, now = frame
        if src not in self.table and len(self.table) >= self.capacity:
            self.table.popitem(last=False)         # throw out the oldest arrival
        self.table[src] = in_port

        if dst == self.BROADCAST or dst not in self.table:
            return [p for p in range(self.ports) if p != in_port]
        out = self.table[dst]
        return [] if out == in_port else [out]


class YourSwitch:
    """Frequency-aware switch with selective admission."""

    BROADCAST = "ff:ff:ff:ff:ff:ff"

    def __init__(self, ports, capacity):
        self.ports = ports
        self.capacity = capacity

        # 실제 forwarding table: mac -> port
        # 이 딕셔너리만 capacity 제한을 받는다.
        self.table = {}

        # 지금까지 관찰한 출발지 MAC의 출현 횟수
        self.frequency = {}

        # 빈도가 같은 항목 중 오래된 것을 선택하기 위한 시각
        self.last_seen = {}

    def handle(self, frame, in_port):
        src, dst, now = frame

        # 현재 출발지가 얼마나 자주 등장했는지 기록한다.
        self.frequency[src] = self.frequency.get(src, 0) + 1
        self.last_seen[src] = now

        if src in self.table:
            # 이미 학습한 장비가 다른 포트로 이동한 경우도 갱신한다.
            self.table[src] = in_port

        elif len(self.table) < self.capacity:
            # 아직 자리가 있으면 바로 학습한다.
            self.table[src] = in_port

        else:
            # 빈도가 가장 낮은 항목을 퇴출 후보로 삼는다.
            # 빈도가 같으면 가장 오래 관찰되지 않은 항목을 고른다.
            victim = min(
                self.table,
                key=lambda mac: (
                    self.frequency.get(mac, 0),
                    self.last_seen.get(mac, 0),
                ),
            )

            # 새 항목이 기존 최저 빈도 항목보다 유용할 때만 교체한다.
            # 같을 때 교체하지 않으면 일회성 단말 때문에 생기는 churn을 줄인다.
            if self.frequency[src] > self.frequency[victim]:
                del self.table[victim]
                self.table[src] = in_port

            # 그렇지 않으면 신규 출발지의 학습을 거절한다.

        # Broadcast와 unknown destination은 flooding한다.
        if dst == self.BROADCAST or dst not in self.table:
            return [
                port
                for port in range(self.ports)
                if port != in_port
            ]

        # 알려진 목적지는 해당 포트 하나로만 보낸다.
        out_port = self.table[dst]

        # 들어온 포트와 목적지 포트가 같으면 다시 보내지 않는다.
        if out_port == in_port:
            return []

        return [out_port]