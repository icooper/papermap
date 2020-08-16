#!/usr/bin/env python

from wsgiref.headers import Headers
from http.client import responses
from werkzeug.serving import run_simple
from pymemcache.client import base as memcache

import click
import pprint
import sqlite3
import os.path
import logging

# super simple WSGI-based MBTiles tile server
class TileServer:

    # initialize the object
    def __init__(self, root):
        self.db = { }
        self.cache = memcache.Client(('localhost', 11211))

        # find MBTiles files
        for f in [f for f in os.listdir(root) if f.endswith('.mbtiles')]:
            key = os.path.splitext(f)[0]
            filename = os.path.join(root, f)
            self.db[key] = sqlite3.connect('file:%s?mode=ro' % filename, uri=True, check_same_thread=False)
            self.db[key].text_factory = bytes
            print('MBTiles file ', filename, ' mapped to URL /', key, '/Z/X/Y.png', sep='')

    def __call__(self, environ, start_response):
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
            content = bytes('\n'.join(self.db.keys()), 'utf-8')
        elif path[0].lower() == 'env':
            content = bytes(pprint.pformat(environ), 'utf-8')
        elif path[0] in self.db:
            if len(path) == 4:
                content = self.tile(environ['PATH_INFO'], *path)
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

    # get the tile from the cache or database
    def tile(self, path, tileset: str, z, x, y):

        # constant for no tile found
        NO_TILE = 'nope'

        # first we check the cache
        png = self.cache.get(path)

        if not png:    

            # check the database
            y = os.path.splitext(y)[0]
            png = self.db[tileset].execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?', (z, x, y)).fetchone()
            png = png and png[0] or NO_TILE

            # add to the cache
            self.cache.set(path, png, expire=3600)

        # return the tile
        return png if png != NO_TILE else None

# run the server
@click.command()
@click.option('--host', default='0.0.0.0', show_default=True, help='Hostname or IP address to listen on')
@click.option('--port', default=8234, show_default=True, help='Port number to listen on')
@click.option('--root', default='data', show_default=True, help='Directory containing MBTiles files')
def cli(host: str, port: int, root: str):
    '''Run a simple MBTiles tile server on the given port number'''

    # disable werkzeug logging
    logging.getLogger('werkzeug').disabled = True

    run_simple(host, port, TileServer(root), use_reloader=True)

# main entry point
if __name__ == '__main__':
    cli()