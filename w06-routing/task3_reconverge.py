#!/usr/bin/env python3
"""Week 6 · Task 3 — Reconverge without recomputing the world.

Textbook §5.2.1, §5.3.

A link flaps. Every router in the area has to decide what changed. `FullRecompute`
does the honest thing: throw the table away and run Dijkstra again, from scratch,
for every event. It is correct and it is what the first implementations did.

It is also why a single flapping link in a large area used to melt the CPU of
every router that could see it.

Beat it:

    python3 bench.py
    python3 bench.py --yours

Correctness first. `bench.py` compares your table against a full recompute after
**every single event**. A router that is fast and wrong black-holes traffic.
"""
import heapq

# The harness counts how many times you run a full SPF. This is the score:
# wall-clock time in Python says more about dictionary overhead than about
# routing, but "how many times did the CPU have to recompute the world" is
# exactly what melted real routers.
SPF_RUNS = 0


def dijkstra_table(graph, source, return_state=False):
    """Reference shortest-path-first.

    기본적으로 {destination: first_hop}을 반환한다.
    return_state=True이면 table, distances, parents를 함께 반환한다.
    """
    global SPF_RUNS
    SPF_RUNS += 1

    best = {source: (0, None)}
    parent = {source: None}
    pq = [(0, source, None)]
    done = set()

    while pq:
        cost, node, first_hop = heapq.heappop(pq)

        if node in done:
            continue

        done.add(node)
        best[node] = (cost, first_hop)

        for nbr, weight in sorted(graph[node].items()):
            if nbr in done:
                continue

            hop = nbr if node == source else first_hop
            new_cost = cost + weight

            if new_cost < best.get(
                nbr, (float("inf"), None)
            )[0]:
                best[nbr] = (new_cost, hop)
                parent[nbr] = node
                heapq.heappush(
                    pq,
                    (new_cost, nbr, hop),
                )

    table = {
        destination: first_hop
        for destination, (_, first_hop) in best.items()
        if destination != source and first_hop
    }

    if not return_state:
        return table

    distances = {
        node: cost
        for node, (cost, _) in best.items()
        if node in done
    }

    parents = {
        node: parent.get(node)
        for node in done
    }

    return table, distances, parents

class FullRecompute:
    """On every event, forget everything and run SPF again."""

    def __init__(self, graph, source):
        self.graph = {n: dict(e) for n, e in graph.items()}
        self.source = source
        self.table = dijkstra_table(self.graph, source)

    def link_change(self, a, b, cost):
        """cost=None means the link went down."""
        if cost is None:
            self.graph[a].pop(b, None)
            self.graph[b].pop(a, None)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost
        self.table = dijkstra_table(self.graph, self.source)


class YourRouter:
    """현재 최단 경로에 영향이 없는 링크 변경은 SPF를 생략한다."""

    def __init__(self, graph, source):
        self.graph = {
            node: dict(edges)
            for node, edges in graph.items()
        }
        self.source = source
        self._recompute()

    @staticmethod
    def _edge(a, b):
        """무방향 링크를 항상 같은 형태로 표현한다."""
        return tuple(sorted((a, b)))

    def _recompute(self):
        """전체 SPF를 실행하고 부가 상태도 갱신한다."""
        (
            self.table,
            self.dist,
            self.parent,
        ) = dijkstra_table(
            self.graph,
            self.source,
            return_state=True,
        )

        self.tree_edges = {
            self._edge(node, parent)
            for node, parent in self.parent.items()
            if parent is not None
        }

    def link_change(self, a, b, cost):
        """cost=None이면 링크 단절, 아니면 추가 또는 비용 변경."""
        old_cost = self.graph[a].get(b)

        # 이미 같은 상태라면 그래프가 실제로 변하지 않는다.
        if old_cost == cost:
            return

        edge = self._edge(a, b)

        # 링크 제거 또는 비용 증가인지 먼저 판별한다.
        removal_or_increase = (
            cost is None
            or (
                old_cost is not None
                and cost > old_cost
            )
        )

        # 그래프에 이벤트를 반영한다.
        if cost is None:
            self.graph[a].pop(b, None)
            self.graph[b].pop(a, None)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost

        # 제거되거나 비싸진 링크가 현재 SPT에 없었다면
        # 현재 최단 경로에는 영향이 없다.
        if removal_or_increase:
            if edge not in self.tree_edges:
                return

            self._recompute()
            return

        # 여기부터는 새 링크 또는 비용 감소다.
        inf = float("inf")
        distance_a = self.dist.get(a, inf)
        distance_b = self.dist.get(b, inf)

        # 양방향 모두 현재 거리보다 엄격하게 길다면
        # 새 링크는 더 짧은 경로를 만들 수 없다.
        if (
            distance_a + cost > distance_b
            and distance_b + cost > distance_a
        ):
            return

        # 더 짧은 경로 또는 동일 비용 경로를 만들 가능성이 있다.
        self._recompute()