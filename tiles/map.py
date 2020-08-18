from . import LonLatToTMS, MBTiles
from abc import ABC

class Map(ABC):

    def render(self, center, zoom, size):
        pass

class TiledMap(Map):

    def __init__(self, filename):
        pass