from abc import ABC
import logging
import os.path
from pymemcache.client import base as memcache
import sqlite3
import xml.etree.ElementTree as ET

# tileset abstract class
class TileSet(ABC):
    
    NO_TILE = '__none__'
    CACHE_EXPR = 86400

    @classmethod
    def factory(cls, source: str, **kwargs):
        tilesets = { }

        # is this an MBTiles file?
        if os.path.isfile(source) and source.endswith('.mbtiles'):
            key = os.path.splitext(os.path.split(source)[1])[0]
            tilesets[key] = MBTiles(source, **kwargs)

        # is this a tileset directory with a tilemapresource.xml file?
        elif os.path.isdir(source) and os.path.isfile(os.path.join(source, 'tilemapresource.xml')):
            key = os.path.split(source)[1]
            tilesets[key] = FileTiles(source, **kwargs)

        # is this a folder full of tilesets?
        elif os.path.isdir(source):
            for f in [f for f in os.listdir(source) if f.endswith('.mbtiles')]:
                key = os.path.splitext(f)[0]
                tilesets[key] = MBTiles(os.path.join(source, f), **kwargs)

            for d in [d for d in os.listdir(source) if os.path.isdir(os.path.join(source, d)) and os.path.isfile(os.path.join(source, d, 'tilemapresource.xml'))]:
                tilesets[d] = FileTiles(os.path.join(source, d), **kwargs)

        return tilesets

    def _debug(self, *args):
        msg = args[0].format(args[1:])
        self._logger.debug('(%s) %s', self._id, msg)

    def _info(self, *args):
        msg = args[0].format(args[1:])
        self._logger.info('(%s) %s', self._id, msg)

    def _warn(self, *args):
        msg = args[0].format(args[1:])
        self._logger.warn('(%s) %s', self._id, msg)

    def _error(self, *args):
        msg = args[0].format(args[1:])
        self._logger.error('(%s) %s', self._id, msg)

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:

        # make a nicer name out of TIFF filenames
        if not ' ' in self._name:
            name = os.path.splitext(self._name)[0]
            name = ' '.join([w.capitalize() for w in name.split('_')])
            name = name[:-5] if name.endswith(' Temp') else name
            if '-' in name:
                nameParts = name.split('-')
                name = '%s (%s)' % ('-'.join(nameParts[:-1]), nameParts[-1].lower())
            self._name = name
        return self._name

    @property
    def minZoom(self) -> int:
        return self._minZoom

    @property
    def maxZoom(self) -> int:
        return self._maxZoom

    @property
    def bounds(self) -> tuple:
        if not isinstance(self._bounds, tuple):
            self._bounds = tuple([float(x) for x in self._bounds.split(',')])
        return self._bounds

    @property
    def center(self) -> tuple:
        if not isinstance(self._center, tuple):
            self._center = tuple([float(x) for x in self._center.split(',')])
        return self._center

    
    # get tile data
    def __call__(self, z, x, y) -> bytes:

        # put together a cache ID
        key = '%s/%s/%s' % (z, x, y)

        # check the cache first if we're using it
        if self._cache:
            tile = self._cache.get(key)
        else:
            tile = None

        # if it wasn't cached
        if not tile:

            # get the tile
            tile = self._tile(z, x, y) or TileSet.NO_TILE

            # add to the cache
            if self._cache and tile:
                self._cache.set(key, tile, expire=TileSet.CACHE_EXPR)

        # return the tile or None if no tile
        return tile if tile != TileSet.NO_TILE else None

# class for directory tree tilesets
class FileTiles(TileSet):

    # constructor
    def __init__(self, dirname, *, logger: logging.Logger=None, useCache=True, cacheAll=False):

        # set up logger
        self._logger = logger or logging.getLogger('FileTiles')

        # parse dirname into id
        self._dirname = dirname
        self._id = os.path.split(self._dirname)[1]

        # read tilemapresource.xml
        tmrfilename = os.path.join(dirname, 'tilemapresource.xml')
        if not os.path.isfile(tmrfilename):
            self._warn('Missing metadata file %s, continuing without metadata' % tmrfilename)
        else:
            # parse XML
            tilemap = ET.parse(tmrfilename).getroot()
            self._info('Parsed %s' % tmrfilename)
            self._name = tilemap.find('./Title').text
            zoomlevels = list(map(lambda x: int(x.attrib['href']), tilemap.findall('./TileSets/TileSet')))
            self._minZoom = min(zoomlevels)
            self._maxZoom = max(zoomlevels)
            tilemapbb = tilemap.find('./BoundingBox')
            minx = float(tilemapbb.attrib['minx'])
            miny = float(tilemapbb.attrib['miny'])
            maxx = float(tilemapbb.attrib['maxx'])
            maxy = float(tilemapbb.attrib['maxy'])
            centerx = (maxx - minx) / 2.0 + minx
            centery = (maxy - miny) / 2.0 + miny
            self._bounds = tuple([minx, miny, maxx, maxy])
            self._center = tuple([centerx, centery, (self._maxZoom - self._minZoom) // 2 + self._minZoom])
            self._info('Name: %s, Zooms: %s-%s, Bounds: %s' % (self.name, self.minZoom, self.maxZoom, self.bounds))

        # set up cache
        self._cache = None
        if useCache:
            try:
                self._cache = memcache.Client(('localhost', 11211), key_prefix=bytes(self._id, 'utf-8'))
                self._debug('Using Memcached')
            except:
                self._warn('Cannot connect to Memcached, continuing without cache')

        # load tiles into cache
        if cacheAll and self._cache:
            for z in [str(z) for z in zoomlevels if os.path.isdir(os.path.join(self._dirname, str(z)))]:
                for x in [x for x in os.listdir(os.path.join(self._dirname, z)) if os.path.isdir(os.path.join(self._dirname, z, x))]:
                    for ypng in [y for y in os.listdir(os.path.join(self._dirname, z, x)) if os.path.isfile(os.path.join(self._dirname, z, x, y))]:
                        y = os.path.splitext(ypng)[0]
                        self._cache.set('%s/%s/%s' % (z, x, y), self._tile(z, x, y), expire=TileSet.CACHE_EXPR)
            self._info('Cached all tile data')

    # get tile
    def _tile(self, z, x, y) -> bytes:

        tilefile = os.path.join(self._dirname, '%s/%s/%s.png' % (z, x, y))
        try:
            fh = open(tilefile, 'rb')
            tile = fh.read()
            fh.close()
        except FileNotFoundError:
            tile = None

        return tile

# class for MBTiles tilesets
class MBTiles(TileSet):

    # constructor
    def __init__(self, filename, *, logger: logging.Logger=None, useCache=True, cacheAll=False):

        # set up logger
        self._logger = logger or logging.getLogger('MBTiles')

        # parse filename into id
        self._filename = filename
        self._id = os.path.splitext(os.path.split(self._filename)[1])[0]

        # connect to MBTiles database
        self._db = sqlite3.connect('file:%s?mode=ro' % self._filename, uri=True, check_same_thread=False)
        self._db.text_factory = bytes
        self._info('Loaded %s' % self._filename)

        # get parameters from mbtiles
        self._name = self._metadata('name')
        self._minZoom = int(self._metadata('minzoom'))
        self._maxZoom = int(self._metadata('maxzoom'))
        self._bounds = self._metadata('bounds')
        self._center = self._metadata('center')
        self._info('Name: %s, Zooms: %s-%s, Bounds: %s' % (self.name, self.minZoom, self.maxZoom, self.bounds))

        # set up cache
        self._cache = None
        if useCache:
            try:
                self._cache = memcache.Client(('localhost', 11211), key_prefix=bytes(self._id, 'utf-8'))
                self._debug('Using Memcached')
            except:
                self._warn('Cannot connect to Memcached, continuing without cache')

        # load tiles into cache
        if cacheAll and self._cache:
            for row in self._db.execute('SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles'):
                z, x, y, tile = row
                self._cache.set('%s/%s/%s' % (z, x, y), tile, expire=TileSet.CACHE_EXPR)
            self._info('Cached all tile data')

    # destructor
    def __del__(self):
        # close the database connection
        self._db.close()

        # close the memcached connection
        if self._cache:
            self._cache.close()

    # get tile
    def _tile(self, z, x, y) -> bytes:
        if self._db:
            tile = self._db.execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?', (z, x, y)).fetchone()
            return tile and tile[0] or None

    # get metadata
    def _metadata(self, key: str) -> str:
        if self._db:
            return self._db.execute('SELECT value FROM metadata WHERE name = ?', (key ,)).fetchone()[0].decode('utf-8')
