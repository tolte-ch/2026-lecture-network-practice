#!/usr/bin/env python3
"""Week 6 · Task 1 — Link state: build the forwarding table yourself.

Textbook §5.2 (link state and distance vector) and §5.3 (OSPF).

Every OSPF router ends up holding the same map of the network, and then each one
computes, alone, where to send a packet for every destination. The computation is
Dijkstra; the output is a forwarding table with **one next hop per destination**,
not a path.

That last part is what makes routing work without anybody carrying a route around
in the packet. Build it.

    python3 task1_linkstate.py --verify
"""
import argparse
import heapq

# Undirected weighted graph: node -> {neighbour: cost}
TOPOLOGY = {
    "u": {"v": 2, "w": 5, "x": 1},
    "v": {"u": 2, "w": 3, "x": 2},
    "w": {"u": 5, "v": 3, "x": 3, "y": 1, "z": 5},
    "x": {"u": 1, "v": 2, "w": 3, "y": 1},
    "y": {"w": 1, "x": 1, "z": 2},
    "z": {"w": 5, "y": 2},
}


def dijkstra(graph, source):
    """Shortest path cost from `source` to every node.

    Return {node: cost}. Unreachable nodes must not appear.
    """
    if source not in graph:
        return {}

    distances = {source: 0}
    pq = [(0, source)]

    while pq:
        cost, node = heapq.heappop(pq)

        # 이미 더 짧은 경로가 발견된 오래된 큐 항목
        if cost != distances.get(node):
            continue

        for neighbor, weight in sorted(graph[node].items()):
            new_cost = cost + weight

            if new_cost < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_cost
                heapq.heappush(pq, (new_cost, neighbor))

    # 검증 코드가 source를 제외한 결과를 기대함
    return {
        node: cost
        for node, cost in distances.items()
        if node != source
    }


def forwarding_table(graph, source):
    """Return {destination: first_hop}."""
    if source not in graph:
        return {}

    # node -> (최소 비용, source에서 출발할 때의 첫 번째 홉)
    best = {source: (0, source)}

    # (비용, 현재 노드, 첫 번째 홉)
    pq = [(0, source, source)]

    while pq:
        cost, node, first_hop = heapq.heappop(pq)

        # 더 좋은 경로가 이미 저장된 오래된 큐 항목
        if best.get(node) != (cost, first_hop):
            continue

        for neighbor, weight in sorted(graph[node].items()):
            new_cost = cost + weight

            # source에서 처음 이동할 때만 이웃이 first_hop이 됨
            new_first_hop = (
                neighbor if node == source else first_hop
            )

            candidate = (new_cost, new_first_hop)
            current = best.get(neighbor)

            # 비용이 더 작거나, 비용이 같고 첫 홉이 사전순으로 빠른 경우
            if current is None or candidate < current:
                best[neighbor] = candidate
                heapq.heappush(
                    pq,
                    (new_cost, neighbor, new_first_hop),
                )

    return {
        destination: first_hop
        for destination, (_, first_hop) in best.items()
        if destination != source
    }

def link_down(graph, a, b):
    """A copy of `graph` with the link a-b removed, in both directions."""
    g = {n: dict(e) for n, e in graph.items()}
    g[a].pop(b, None)
    g[b].pop(a, None)
    return g


# ------------------------------------------------------------------- harness
# Costs from the textbook's worked example, §5.2.1
EXPECTED_COST_U = {"v": 2, "w": 3, "x": 1, "y": 2, "z": 4}
EXPECTED_TABLE_U = {"v": "v", "w": "x", "x": "x", "y": "x", "z": "x"}


def verify():
    fails = 0
    try:
        cost = dijkstra(TOPOLOGY, "u")
    except NotImplementedError:
        print("  dijkstra is still a stub"); return 1
    ok = cost == EXPECTED_COST_U
    print(f"  {'ok  ' if ok else 'FAIL'}  costs from u: {cost}")
    if not ok:
        print(f"        expected {EXPECTED_COST_U}")
    fails += not ok

    try:
        table = forwarding_table(TOPOLOGY, "u")
    except NotImplementedError:
        print("  forwarding_table is still a stub"); return 1
    ok = table == EXPECTED_TABLE_U
    print(f"  {'ok  ' if ok else 'FAIL'}  table at u:  {table}")
    if not ok:
        print(f"        expected {EXPECTED_TABLE_U}")
    fails += not ok

    # every node should be able to reach every other
    for n in TOPOLOGY:
        t = forwarding_table(TOPOLOGY, n)
        missing = set(TOPOLOGY) - {n} - set(t)
        bad = [d for d, h in t.items() if h not in TOPOLOGY[n]]
        ok = not missing and not bad
        print(f"  {'ok  ' if ok else 'FAIL'}  table at {n} covers all, hops are neighbours"
              + (f"  missing={missing} bad={bad}" if not ok else ""))
        fails += not ok

    # cutting a link must change somebody's mind
    cut = link_down(TOPOLOGY, "u", "x")
    after = forwarding_table(cut, "u")
    ok = after != table
    print(f"  {'ok  ' if ok else 'FAIL'}  u reroutes when u-x goes down: {after}")
    fails += not ok

    print(f"\n  {'all ok' if not fails else str(fails) + ' failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    raise SystemExit(verify() if a.verify else p.print_help())
