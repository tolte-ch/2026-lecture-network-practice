#!/usr/bin/env python3
"""Week 7 · Task 1 — Build a learning switch.

Textbook §6.4.3 (link-layer switches, self-learning) and §6.4.1 (MAC addresses).

A switch is handed a frame and has to decide which ports to send it out of.
Nobody configures it. It works out the map by **watching where frames come
from**, which is the whole idea of self-learning, and it is about thirty lines.

The thirty lines are not the hard part. The hard part is what it does when it
does not know, and what happens to the things it learned when a machine moves.

    python3 task1_switch.py --verify
"""
import argparse


class Switch:
    BROADCAST = "ff:ff:ff:ff:ff:ff"
    AGE_SECONDS = 300

    def __init__(self, ports):
        self.ports = ports
        self._entries = {}       # mac -> (port, last_seen)
        self._now = 0.0

    def _expire(self):
        """현재 시각을 기준으로 오래된 MAC 항목을 제거한다."""
        expired = [
            mac
            for mac, (_, last_seen) in self._entries.items()
            if self._now - last_seen > self.AGE_SECONDS
        ]

        for mac in expired:
            del self._entries[mac]

    def handle(self, frame, in_port):
        src_mac, dst_mac, now = frame

       # 현재 시각을 갱신하고 오래된 정보를 먼저 제거한다.
        self._now = now
        self._expire()

        # 출발지 MAC을 학습한다.
        # 같은 MAC이 다른 포트에서 보이면 기존 정보를 덮어쓴다.
        self._entries[src_mac] = (in_port, now)

        # 브로드캐스트는 입력 포트를 제외한 모든 포트로 전달한다.
        if dst_mac == self.BROADCAST:
            return [
                port for port in range(self.ports)
                if port != in_port
            ]

        # 알려지지 않은 목적지는 플러딩한다.
        destination = self._entries.get(dst_mac)
        if destination is None:
            return [
                port for port in range(self.ports)
                if port != in_port
            ]

        out_port, _ = destination

        # 목적지 포트가 입력 포트와 같으면 아무 데도 보내지 않는다.
        if out_port == in_port:
            return []

        # 알려진 목적지에는 해당 포트로만 전달한다.
        return [out_port]

    def table(self):
        self._expire()

        return {
            mac: port
            for mac, (port, _) in self._entries.items()
        }


# ------------------------------------------------------------------- harness
A, B, C = "00:00:00:00:00:0a", "00:00:00:00:00:0b", "00:00:00:00:00:0c"
BC = Switch.BROADCAST


def verify():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<46} {got}"
              + ("" if ok else f"   want {want}"))
        fails += not ok

    try:
        s = Switch(4)
    except NotImplementedError:
        print("  Switch is still a stub"); return 1

    # A talks to B. Nobody knows B yet, so it floods - but not back to port 0.
    check("unknown destination floods",
          s.handle((A, B, 0.0), 0), [1, 2, 3])
    # Now B answers from port 2. The switch has seen A, so it forwards precisely.
    check("known destination is not flooded",
          s.handle((B, A, 1.0), 2), [0])
    check("learned both",
          s.table(), {A: 0, B: 2})
    # Broadcast always goes everywhere except back.
    check("broadcast floods",
          s.handle((A, BC, 2.0), 0), [1, 2, 3])
    # A frame for yourself must not come back out of the port it came in on.
    check("never back out the arrival port",
          s.handle((C, A, 3.0), 0), [])
    # B moves to port 3. The switch must believe the new evidence.
    check("station moved, table follows",
          (s.handle((B, A, 4.0), 3), s.table()[B]), ([0], 3))
    # Nothing heard from A for longer than AGE_SECONDS - it must be forgotten.
    s.handle((C, BC, 400.0), 1)
    check("aged-out entry is gone", A in s.table(), False)

    print(f"\n  {'all ok' if not fails else str(fails) + ' failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    raise SystemExit(verify() if a.verify else p.print_help())
