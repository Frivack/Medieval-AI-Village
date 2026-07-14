# backend/world/tiles.py
from enum import Enum


class TileType(str, Enum):
    GRASS = "grass"
    WATER = "water"
    FOREST = "forest"   # resource: wood
    FIELD = "field"     # resource: crops
    WALL = "wall"       # building wall
    FLOOR = "floor"     # building interior
    DOOR = "door"       # building entrance
    BRIDGE = "bridge"


# Which tiles an agent can stand on / walk through.
WALKABLE = {
    TileType.GRASS,
    TileType.FOREST,
    TileType.FIELD,
    TileType.FLOOR,
    TileType.DOOR,
    TileType.BRIDGE,
}

# One-character codes for compact map serialization (GET /map).
TILE_CHAR = {
    TileType.GRASS: ".",
    TileType.WATER: "~",
    TileType.FOREST: "T",
    TileType.FIELD: "f",
    TileType.WALL: "#",
    TileType.FLOOR: "_",
    TileType.DOOR: "D",
    TileType.BRIDGE: "=",
}
