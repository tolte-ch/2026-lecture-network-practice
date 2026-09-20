#!/usr/bin/env python3
"""Week 4 · Task 1 — Build reliable delivery on top of an unreliable channel.

Textbook §3.4 (reliable data transfer) and §3.5 (TCP's sequence numbers).

`UnreliableChannel` below loses packets, reorders them, duplicates them, and
delays them. It is the network as §3.4 models it. Your job is to move a file
across it and have the bytes arrive intact and in order.

That is the whole of TCP's reliability story with the congestion control taken
out, and it is worth building once by hand before you ever trust a socket again.

    python3 task1_rdt.py --verify
"""
import argparse, hashlib, random

PAYLOAD = 8            # bytes per packet - small, so you see the sequencing


class UnreliableChannel:
    """Loses 10%, duplicates 3%, reorders, and delays. Deterministic by seed.

    You may not make it nicer. You may not read its internals. It is the only
    way your sender can reach your receiver.
    """

    def __init__(self, seed=246, loss=0.10, dup=0.03, reorder=0.10):
        self.rng = random.Random(seed)
        self.loss, self.dup, self.reorder = loss, dup, reorder
        self.wire = []          # packets in flight, in no particular order
        self.stats = {"sent": 0, "lost": 0, "duplicated": 0, "delivered": 0}

    def send(self, packet):
        """Hand a packet to the network. It may never come out."""
        self.stats["sent"] += 1
        if self.rng.random() < self.loss:
            self.stats["lost"] += 1
            return
        copies = 2 if self.rng.random() < self.dup else 1
        self.stats["duplicated"] += copies - 1
        for _ in range(copies):
            if self.rng.random() < self.reorder and self.wire:
                self.wire.insert(self.rng.randrange(len(self.wire)), packet)
            else:
                self.wire.append(packet)

    def receive(self):
        """Take the next packet out, or None if the network has nothing."""
        if not self.wire:
            return None
        self.stats["delivered"] += 1
        return self.wire.pop(0)


class Sender:
    """Stop-and-wait sender."""

    def __init__(self, data_channel, ack_channel, data):
        self.data_channel = data_channel
        self.ack_channel = ack_channel

        # 2,000바이트를 PAYLOAD(8바이트) 단위로 분할
        self.packets = [
            data[i:i + PAYLOAD]
            for i in range(0, len(data), PAYLOAD)
        ]

        # 현재 ACK를 기다리는 패킷 번호
        self.seq = 0

        # ACK가 오지 않을 때 재전송하기 위한 단순 타이머
        self.timer = 0
        self.timeout = 3

    def step(self):
        """한 단계 진행하고, 모든 ACK를 받으면 False를 반환한다."""

        # ACK 채널에서 ACK 하나를 확인
        ack = self.ack_channel.receive()

        if ack is not None:
            packet_type, ack_seq = ack

            # 현재 기다리는 패킷의 ACK만 인정한다.
            # 과거 패킷의 중복 ACK는 무시한다.
            if packet_type == "ACK" and ack_seq == self.seq:
                self.seq += 1
                self.timer = 0

        # 모든 데이터 패킷의 ACK를 받음
        if self.seq >= len(self.packets):
            return False

        # 처음 보내거나 timeout이 발생한 경우 전송
        if self.timer <= 0:
            packet = ("DATA", self.seq, self.packets[self.seq])
            self.data_channel.send(packet)
            self.timer = self.timeout
        else:
            self.timer -= 1

        return True


class Receiver:
    """Stop-and-wait receiver."""

    def __init__(self, data_channel, ack_channel):
        self.data_channel = data_channel
        self.ack_channel = ack_channel

        # 다음에 받아야 하는 패킷 번호
        self.expected_seq = 0

        # 순서대로 확정된 payload
        self.received = []

    def step(self):
        packet = self.data_channel.receive()

        if packet is None:
            return True

        packet_type, seq, payload = packet

        if packet_type != "DATA":
            return True

        if seq == self.expected_seq:
            # 정확히 다음 패킷일 때만 데이터를 추가
            self.received.append(payload)
            self.expected_seq += 1

            # 방금 정상적으로 받은 패킷 번호를 ACK
            self.ack_channel.send(("ACK", seq))

        elif seq < self.expected_seq:
            # 이미 처리한 데이터가 재전송된 경우:
            # 데이터는 다시 추가하지 않고 ACK만 다시 전송
            self.ack_channel.send(("ACK", seq))

        else:
            # Stop-and-wait에서는 보통 발생하지 않지만,
            # 미래 번호가 왔다면 받아들이지 않는다.
            if self.expected_seq > 0:
                self.ack_channel.send(
                    ("ACK", self.expected_seq - 1)
                )

        return True

    def data(self):
        return b"".join(self.received)


# ------------------------------------------------------------------- harness
def verify(seed=246, size=2000, max_steps=200_000):
    original = bytes(random.Random(seed).getrandbits(8) for _ in range(size))
    up, down = UnreliableChannel(seed), UnreliableChannel(seed + 1)

    # Data goes out over `up`, ACKs come back over `down`. Both are unreliable.
    sender = Sender(up, down, original)
    receiver = Receiver(up, down)

    for _ in range(max_steps):
        alive = sender.step()
        receiver.step()
        if not alive and len(receiver.data() or b"") >= size:
            break

    got = receiver.data() or b""
    ok = hashlib.sha256(got).hexdigest() == hashlib.sha256(original).hexdigest()
    print(f"  bytes    sent {size}   received {len(got)}")
    print(f"  channel  {up.stats}")
    print(f"  result   {'IDENTICAL' if ok else 'CORRUPTED OR INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--seed", type=int, default=246)
    a = p.parse_args()
    raise SystemExit(verify(a.seed) if a.verify else p.print_help())
