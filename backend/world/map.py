# backend/world/map.py
# The village map: a 100x50 tile grid, generated deterministically in code
# so the world is identical on every run (no random seed to manage yet).
from backend.config import MAP_WIDTH, MAP_HEIGHT
from backend.world.tiles import TileType, WALKABLE, TILE_CHAR


class Building:
    def __init__(self, name: str, x: int, y: int, width: int, height: int):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        # Door: middle of the south wall, one tile agents pass through.
        self.door = (x + width // 2, y + height - 1)
        # Where an agent stands when "inside" the building.
        self.interior = (x + width // 2, y + height // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


class VillageMap:
    def __init__(self):
        self.width = MAP_WIDTH
        self.height = MAP_HEIGHT
        self.grid = [[TileType.GRASS for _ in range(self.width)] for _ in range(self.height)]
        self.buildings: dict[str, Building] = {}
        self._generate()

    # ---- generation -------------------------------------------------

    def _generate(self):
        # River: vertical band on the east side, crossed by one bridge.
        for y in range(self.height):
            for x in range(70, 73):
                self.grid[y][x] = TileType.WATER
        for y in range(24, 27):
            for x in range(70, 73):
                self.grid[y][x] = TileType.BRIDGE

        # Forest: east of the river (wood-gathering area).
        for y in range(5, 21):
            for x in range(78, 96):
                self.grid[y][x] = TileType.FOREST

        # Farmland next to the farm house.
        for y in range(16, 23):
            for x in range(10, 26):
                self.grid[y][x] = TileType.FIELD

        # Buildings (name, x, y, w, h) — walls, floor interior, south door.
        self._place_building(Building("Farm", 10, 8, 8, 6))
        self._place_building(Building("Smithy", 40, 10, 6, 5))
        self._place_building(Building("Market", 50, 25, 10, 8))
        self._place_building(Building("Inn", 30, 30, 8, 6))

    def _place_building(self, b: Building):
        for y in range(b.y, b.y + b.height):
            for x in range(b.x, b.x + b.width):
                on_edge = (x == b.x or x == b.x + b.width - 1
                           or y == b.y or y == b.y + b.height - 1)
                self.grid[y][x] = TileType.WALL if on_edge else TileType.FLOOR
        dx, dy = b.door
        self.grid[dy][dx] = TileType.DOOR
        self.buildings[b.name] = b

    # ---- queries -----------------------------------------------------

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.grid[y][x] in WALKABLE

    def tile_at(self, x: int, y: int) -> TileType:
        return self.grid[y][x]

    def building_at(self, x: int, y: int):
        for b in self.buildings.values():
            if b.contains(x, y):
                return b
        return None

    # ---- serialization ----------------------------------------------

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "legend": {c: t.value for t, c in TILE_CHAR.items()},
            "rows": ["".join(TILE_CHAR[t] for t in row) for row in self.grid],
            "buildings": [
                {"name": b.name, "x": b.x, "y": b.y,
                 "width": b.width, "height": b.height, "door": list(b.door)}
                for b in self.buildings.values()
            ],
        }


# Single shared instance — the map is static world data.
village_map = VillageMap()
