# backend/world/pathfinding.py
# A* on the tile grid. 4-directional movement, Manhattan-distance heuristic
# (admissible for 4-dir grids, so the result is an optimal path).
import heapq

from backend.world.map import VillageMap


def find_path(vmap: VillageMap, start: tuple, goal: tuple) -> list:
    """Return a list of (x, y) steps from start to goal, excluding start.

    Empty list means already at goal OR no path exists — callers that need
    to distinguish can check start == goal first.
    """
    if start == goal:
        return []
    if not vmap.is_walkable(*goal):
        return []

    open_heap = [(0, start)]           # (f_score, node)
    came_from = {}
    g_score = {start: 0}

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == goal:
            return _reconstruct(came_from, current)

        cx, cy = current
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if not vmap.is_walkable(nx, ny):
                continue
            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get((nx, ny), float("inf")):
                came_from[(nx, ny)] = current
                g_score[(nx, ny)] = tentative_g
                f = tentative_g + abs(nx - goal[0]) + abs(ny - goal[1])
                heapq.heappush(open_heap, (f, (nx, ny)))

    return []  # unreachable


def _reconstruct(came_from: dict, node: tuple) -> list:
    path = [node]
    while node in came_from:
        node = came_from[node]
        path.append(node)
    path.reverse()
    return path[1:]  # drop the start tile
