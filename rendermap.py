#!/usr/bin/env python

import click
from tiles import LonLatToTMS

@click.command()
@click.option('--tileset', default='data/grand_mesa.mbtiles', show_default=True, help='Use this tileset')
@click.option('--output', default='render.png', show_default=True)
@click.option('--zoom', default=12, show_default=True)
@click.argument('lonlat', default='-107.98118591308595,39.02785219375274')
def cli(tileset: str, output: str, zoom: int, lonlat: str):
    '''Renders a map of the specified location to the specified file.'''
    inputCoord = [float(x) for x in lonlat.split(',')]
    tmsCoord = LonLatToTMS(zoom, *inputCoord)

    # spherical: -12020410.631098535, 4725661.945959807
    # TMS: 12/819/2531

    print(inputCoord, '@', zoom, '=>', tmsCoord)

# main entry point
if __name__ == '__main__':
    cli()