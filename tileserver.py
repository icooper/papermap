#!/usr/bin/env python

from http.client import responses
from pymemcache.client import base as memcache
from werkzeug.serving import run_simple
from wsgiref.headers import Headers
from tiles import TileSet

import click
import json
import logging
import os.path
import pprint
import sqlite3

# super simple WSGI-based MBTiles tile server
class TileServer:

    # initialize the object
    def __init__(self, source: str, *, logger: logging.Logger=None, useCache=True, cacheAll=False):
        self.source = source
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info('TileServer created')
        self.tileset = { }
        self.useCache = useCache
        self.cacheAll = cacheAll
        self.initialized = False

        if self.useCache:
            self.cache = memcache.Client(('localhost', 11211))
            self.logger.info('Connected to memcached')
 
        if self.useCache and self.cacheAll:
            self.loadmaps()
        
    def loadmaps(self):

        # clear our maps
        self.tileset.clear()

        # clear cache
        if self.useCache:
            self.cache.flush_all()
            self.logger.debug('Cleared cache')

        # load the tilesets
        self.tileset = TileSet.factory(self.source, logger=self.logger, useCache=self.useCache, cacheAll=self.cacheAll)

        # we are now initialized
        self.initialized = True

    def __call__(self, environ, start_response):
        if not self.initialized:
            self.loadmaps()
        code, headers, content = self.dispatch(environ, start_response, Headers([]))
        headers.setdefault('Content-Length', str(len(content)))
        start_response('%s %s' % (code, responses[code]), headers.items())
        return [content]

    # process the incoming request
    def dispatch(self, environ, start_response, headers):
        code = 200
        path = environ['PATH_INFO'][1:].split('/')
        if path[0] == '':
            headers.setdefault('Content-Type', 'text/plain')
            content = bytes('\n'.join(self.tileset.keys()), 'utf-8')
        elif path[0].lower() == 'env':
            headers.setdefault('Content-Type', 'text/plain')
            content = bytes(pprint.pformat(environ), 'utf-8')
        elif path[0].lower() == 'reload':
            self.loadmaps()
            headers.setdefault('Content-Type', 'text/plain')
            content = bytes('OK', 'utf-8')
        elif path[0].lower() == 'maps.json':
            headers.setdefault('Content-Type', 'application/json')
            headers.setdefault('Access-Control-Allow-Origin', '*')
            content = bytes(self.maps(environ), 'utf-8')
        elif path[0] in self.tileset:
            if len(path) == 4:
                content = self.tile(*path)
                if content:
                    headers.setdefault('Content-Type', 'image/png')
                    headers.setdefault('Cache-Control', 'public, max-age=3600')
                else:
                    code = 404
                    headers.setdefault('Content-Type', 'text/plain')
                    content = bytes('tile at %s not found' % environ['PATH_INFO'], 'utf-8')
            else:
                code = 400
                headers.setdefault('Content-Type', 'text/plain')
                content = bytes('bad request %s' % environ['PATH_INFO'], 'utf-8')
        else:
            code = 404
            headers.setdefault('Content-Type', 'text/plain')
            content = bytes('tileset %s not found' % path[0], 'utf-8')

        return (code, headers, content)

    # list the supported maps
    def maps(self, environ):
        maplist = { 
            'maps': []
        }
        for key in self.tileset.keys():
            maplist['maps'].append({
                'id': key,
                'name': self.tileset[key].name,
                'minZoom': self.tileset[key].minZoom,
                'maxZoom': self.tileset[key].maxZoom,
                'bounds': self.tileset[key].bounds,
                'urlTemplate': '%s://%s/%s/{z}/{x}/{y}.png' % (environ['wsgi.url_scheme'], environ['HTTP_HOST'], key)
            })

        self.logger.info('Maps JSON requested')

        return json.dumps(maplist, indent=4)

    # get the tile from the cache or database
    def tile(self, tileset: str, z, x, y):
        y = os.path.splitext(y)[0]
        return self.tileset[tileset](int(z), int(x), int(y))

# run the server
@click.command()
@click.option('--host', default='0.0.0.0', show_default=True, help='Hostname or IP address to listen on')
@click.option('--port', default=8234, show_default=True, help='Port number to listen on')
@click.option('--no-cache', default=False, is_flag=True, show_default=True, help='Do not use Memcached for the tile cache')
@click.option('--cache-all', default=False, is_flag=True, show_default=True, help='Cache all tiles to memory right away')
@click.option('--verbose', default=False, is_flag=True, show_default=True, help='Show lots of messages')
@click.argument('source', default='data')
def cli(host: str, port: int, no_cache: bool, cache_all: bool, verbose: bool, source: str):
    '''Run a simple MBTiles tile server on the given port number'''

    def logFilter(r: logging.LogRecord):
        if r.msg.startswith(' * '):
            r.msg = r.msg[3:]
        return 0 if r.msg.endswith(('200 -', '404 -')) and not verbose else 1

    # configure logging  
    logHandler = logging.StreamHandler()
    logHandler.setLevel(logging.DEBUG)
    logHandler.setFormatter(logging.Formatter('%(name)s\t%(message)s'))
    logHandler.addFilter(logFilter)

    for logger in [logging.getLogger(x) for x in [__name__, 'werkzeug']]:
        logger.setLevel(logHandler.level)
        logger.addHandler(logHandler)

    # run the tile server
    run_simple(host, port, TileServer(source, useCache=not no_cache, cacheAll=cache_all), use_reloader=True)

# main entry point
if __name__ == '__main__':
    cli()