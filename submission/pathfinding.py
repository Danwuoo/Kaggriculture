"""Tiny all-pairs BFS cache. LOCKED tiles are deliberately traversable."""

from collections import deque

from constants import MOVES, shed_tiles


_CACHES = {}


class DistanceCache:
    def __new__(cls, size=10):
        if size in _CACHES:
            return _CACHES[size]
        obj = super().__new__(cls)
        _CACHES[size] = obj
        return obj

    def __init__(self, size=10):
        if getattr(self, "size", None) == size:
            return
        self.size = size
        self._dist = {}
        self._next = {}
        for y in range(size):
            for x in range(size):
                self._bfs((x, y))

    def _bfs(self, source):
        queue = deque([source])
        dist = {source: 0}
        first = {source: None}
        # Fixed ordering is part of deterministic behavior.
        for_pos = (("NORTH", 0, -1), ("WEST", -1, 0), ("EAST", 1, 0), ("SOUTH", 0, 1))
        while queue:
            x, y = queue.popleft()
            for op, dx, dy in for_pos:
                nxt = (x + dx, y + dy)
                if not (0 <= nxt[0] < self.size and 0 <= nxt[1] < self.size) or nxt in dist:
                    continue
                dist[nxt] = dist[(x, y)] + 1
                first[nxt] = op if (x, y) == source else first[(x, y)]
                queue.append(nxt)
        self._dist[source] = dist
        self._next[source] = first

    def distance(self, start, goal):
        return self._dist.get(tuple(start), {}).get(tuple(goal), 10 ** 6)

    def nearest(self, start, goals):
        goals = tuple(goals)
        if not goals:
            return None
        return min(goals, key=lambda goal: (self.distance(start, goal), goal[1], goal[0]))

    def next_action(self, start, goal):
        if tuple(start) == tuple(goal):
            return ["PASS"]
        op = self._next.get(tuple(start), {}).get(tuple(goal))
        return [op] if op in MOVES else ["PASS"]

    def distance_to_shed(self, pos):
        return min(self.distance(pos, target) for target in shed_tiles(self.size))

