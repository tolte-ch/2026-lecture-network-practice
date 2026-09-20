#!/usr/bin/env python3
"""Week 4 · Task 3 — Beat the fixed window.

Textbook §3.7.

`FixedWindow` is a sender that never adapts. It picks a window and keeps it,
forever, no matter what the network says back. It is not a strawman: it is what
you get if you skip congestion control entirely, and it was the internet's
actual failure mode in October 1986.

Write `YourControl` and beat it on the harness:

    python3 bench.py
    python3 bench.py --yours

The interface is two events and one number:

    .window        how many packets you are willing to have in flight
    .on_ack()      one packet made it there and back
    .on_loss()     a packet was dropped, or timed out waiting for its ACK

That is all the information a real TCP sender has. It cannot see the queue,
it cannot see the link rate, and neither can you. You infer them from these
two events, which is the entire idea of §3.7.
"""


class FixedWindow:
    """Send 64 packets at a time and never listen."""

    def __init__(self):
        self.window = 64

    def on_ack(self):
        pass

    def on_loss(self):
        pass


class YourControl:
    """Slow start followed by AIMD congestion control."""

    def __init__(self):
        # 처음에는 하나의 패킷부터 시작
        self.window = 1.0

        # BDP = capacity 1 packet/slot × RTT 20 slots = 20 packets
        # 여기까지는 slow start로 빠르게 증가
        self.ssthresh = 20.0

        # 손실이 발생하면 기존 윈도의 70%로 감소
        self.backoff = 0.70

    def on_ack(self):
        if self.window < self.ssthresh:
            # Slow start:
            # ACK 하나당 window를 1 증가시키므로 RTT마다 약 두 배 증가
            self.window = min(
                self.ssthresh,
                self.window + 1.0
            )
        else:
            # Congestion avoidance:
            # ACK 하나당 1/window만큼 증가하므로
            # RTT마다 전체 window가 약 1 증가
            self.window += 1.0 / self.window

    def on_loss(self):
        # Multiplicative decrease
        self.ssthresh = max(
            1.0,
            self.window * self.backoff
        )
        self.window = self.ssthresh
