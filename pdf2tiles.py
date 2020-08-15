#!/usr/bin/env python

from typing import List, Tuple, Dict

import click
import errno
import json
import math
import os.path
import pprint
import re
import subprocess
import sys

# these might have to be updated
GDALINFO = '/usr/bin/gdalinfo'
GDALTRANS = '/usr/bin/gdal_translate'
GDALTILES = '/usr/bin/gdal2tiles.py'

# understood GeoPDF types
TYPE_USFS = 'USFS Quad'
TYPE_USGS = 'USGS Quad'
TYPE_MVUM = 'USFS MVUM'

# run a command and capture the output
def capture(args: List):
    process = subprocess.run(args, stdout=subprocess.PIPE)
    return process.stdout.decode('utf-8')

# run a command and pass-through the output in real time
def passthru(args: List, *, prefix=False):
    process = subprocess.Popen(args=args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if prefix:
        sys.stdout.write('    ')
        sys.stdout.write(' '.join(map(lambda x: '"{}"'.format(x) if x.find(' ') >= 0 else x, args)))
        sys.stdout.write('\n    %s: ' % args[0])
    lastchar = ''
    for c in iter(lambda: process.stdout.read(1), b''):
        char = c.decode('utf-8')
        if prefix and lastchar == '\n':
            sys.stdout.write('    %s: ' % args[0])
        sys.stdout.write(char)
        sys.stdout.flush() # might be slow but useful here
        lastchar = char
    return process.wait()

# analyze the gdalinfo output for a GeoPDF file
def analyze(infile: str, *, passthru=False, dpi=0, max_zoom=0):

    # die if the file doesn't exist
    if not os.path.isfile(infile):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), infile)

    # use gdalinfo to get GeoPDF file information
    gdalinfo = json.loads(capture([GDALINFO, '-nofl', '-json', '-mdd', 'layers', infile]))
    if passthru:
        print(pprint.pformat(gdalinfo, indent=2, compact=False))

    # set up output dict
    output = {
        # GDAL defaults
        'dpi': 150,

        # from gdalinfo
        'filename': infile,
        'description': gdalinfo['description'],
        'format': '/'.join((gdalinfo['driverShortName'], gdalinfo['driverLongName'])),
        'size': gdalinfo['size'], # reported at 150 dpi
        'bands': max(map(lambda x: x['band'], gdalinfo['bands'])),

        # computed properties
        'knownType': None,
        'layersOn': None,
        'layersOff': None,
        'degWidth': 0.0,
        'degHeight': 0.0,
        'minZoom': 5,
        'maxZoom': 14
    }

    # set up map type detection and details
    map_types = {
        TYPE_USGS: {
            'layer': 'Map_Frame',
            'layersOn': None,
            'layersOff': ['Images', 'Images.Orthoimage'],
            'suggestedZoom': 16
        },
        TYPE_USFS: {
            'layer': 'Quadrangle',
            'layersOn': None,
            'layersOff': None,
            'suggestedZoom': 16
        },
        TYPE_MVUM: {
            'layer': 'Vicinity_Map',
            'layersOn': None,
            'layersOff': None,
            'suggestedZoom': 14
        }
    }

    # figure out the type based on the layers
    if 'layers' in gdalinfo['metadata']:
        for map_type in map_types.keys():
            if map_types[map_type]['layer'] in gdalinfo['metadata']['layers'].values():

                # set some output properties
                output['knownType'] = map_type
                output['layersOn'] = map_types[map_type]['layersOn']
                output['layersOff'] = map_types[map_type]['layersOff']

                # set the suggested max zoom
                if max_zoom == 0:
                    max_zoom = map_types[map_type]['suggestedZoom']
                break

    # find the size of the map
    coords = gdalinfo['wgs84Extent']['coordinates'][0]
    output['degWidth'] = max(map(lambda x: x[0], coords)) - min(map(lambda x: x[0], coords))
    output['degHeight'] = max(map(lambda x: x[1], coords)) - min(map(lambda x: x[1], coords))

    # if we have a specified max zoom, figure out the DPI required to achieve this zoom
    if max_zoom > 0:
        dpi = math.ceil(2 ** (max_zoom + 8) / 180 * output['degHeight'] / output['size'][1] * output['dpi'])
        output['size'] = list(map(lambda x: int(x * dpi / output['dpi']), output['size']))
        output['dpi'] = dpi
        output['maxZoom'] = max_zoom

    # if we have a specified DPI, figure out the maximum feasible zoom level at that DPI
    elif dpi > 0:
        output['size'] = list(map(lambda x: int(x * dpi / output['dpi']), output['size']))
        output['dpi'] = dpi
        output['maxZoom'] = int(math.log2(output['size'][1] / output['degHeight'] * 180) - 8)

    # make sure minimum zoom level is sane
    output['minZoom'] = min(output['minZoom'], max(output['maxZoom'] - 3, 0))
    
    return output

# rasterize a PDF into a TIFF
def rasterize(analysis: Dict, infile: str, outfile: str):
    if analysis['format'] == 'GTiff/GeoTIFF':
        print('Warning: Input file', infile, 'is already in GeoTIFF format.')
        return infile

    elif not analysis['format'] == 'PDF/Geospatial PDF':
        print('Error: Input file', infile, 'is not in GeoPDF format.')
        return None

    else:
        args = [
            GDALTRANS, infile, outfile,
            '--config', 'GDAL_PDF_BANDS', str(analysis['bands']),
            '--config', 'GDAL_PDF_DPI', str(analysis['dpi'])
        ]
        if analysis['layersOn']:
            args.append('--config')
            args.append('GDAL_PDF_LAYERS')
            args.append(','.join(analysis['layersOn']))
        elif analysis['layersOff']:
            args.append('--config')
            args.append('GDAL_PDF_LAYERS_OFF')
            args.append(','.join(analysis['layersOff']))

        # run gdal_transform to rasterize the PDF
        print('Rasterizing', infile, 'to', outfile, 'at', analysis['dpi'], 'dpi')
        passthru(args, prefix=True)
        return outfile

# tile a TIFF file
def tile(analysis: Dict, infile: str, outdir: str, min_zoom=0, max_zoom=0):
    
    # set up zoom range
    if min_zoom == 0:
        min_zoom = analysis['minZoom']
    if max_zoom == 0:
        max_zoom = analysis['maxZoom']
    zoom = '%d-%d' % (min_zoom, max_zoom)

    if min_zoom <= 0 or max_zoom <= min_zoom:
        print('Warning: zoom levels make no sense, using defaults.')
        zoom = '%d-%d' % (analysis['minZoom'], analysis['maxZoom'])

    args = [
        GDALTILES,
        '-z', zoom,
        '-e',
        infile, outdir
    ]
    
    print('Tiling', infile, 'to', outdir, 'with zoom', zoom)
    passthru(args, prefix=True)
    return outdir

@click.group()
def cli():
    '''Utility to convert GeoPDF to GeoTIFF or tileset using GDAL'''
    pass

@click.command()
@click.option('--dpi', default=0, help='Hypothetical rasterizing resolution')
@click.option('--max-zoom', default=0, help='Hypothetical maximum zoom level')
@click.option('--debug', default=False, is_flag=True, help='Show debug information')
@click.argument('infile')
def info(dpi: int, max_zoom: int, debug: bool, infile: str):
    '''Displays GeoPDF file information'''
    analysis = analyze(infile, passthru=debug, dpi=dpi, max_zoom=max_zoom)
    if debug:
        print(pprint.pformat(analysis, indent=4))

    # is this not a GeoPDF file?
    if analysis['format'] != 'PDF/Geospatial PDF':
        print('Error: Input file', infile, 'is not in GeoPDF format.')
    
    else:
        # print out some information
        print('Filename:', analysis['filename'])
        print('Format:', analysis['format'])
        print('Map Type:', analysis['knownType'] if analysis['knownType'] else 'Unknown')
        print('Resolution:', analysis['dpi'], 'dpi')
        print('Rasterized Size:', tuple(analysis['size']))
        print('Zoom Levels:', '%d-%d' % (analysis['minZoom'], analysis['maxZoom']))

@click.command()
@click.option('--dpi', default=0, help='PDF rasterizing resolution')
@click.option('--max-zoom', default=0, help='Maximum zoom level')
@click.argument('infile')
@click.argument('outfile', default='__auto__')
def tiff(dpi: int, max_zoom: int, infile: str, outfile: str):
    '''Converts GeoPDF into GeoTIFF'''

    # get ouptut path if not specified
    if outfile == '__auto__':
        outfile = '%s.tiff' % os.path.splitext(infile)[0]

    # make sure the output path is not an existing directory
    if os.path.isdir(outfile):
        print('Error: Output file', outfile, 'is a directory.')

    # rasterize the file
    else:
        analysis = analyze(infile, dpi=dpi, max_zoom=max_zoom)

        if analysis['format'] == 'PDF/Geospatial PDF':
            rasterize(analysis, infile, outfile, dpi)
        else:
            print('Error: Input file', infile, 'is not in GeoPDF format.')

@click.command()
@click.option('--dpi', default=0, help='PDF rasterizing resolution')
@click.option('--min-zoom', default=0, help='Minimum zoom level')
@click.option('--max-zoom', default=0, help='Maximum zoom level')
@click.argument('infile')
@click.argument('outdir', default='__auto__')
def tileset(dpi: int, min_zoom: int, max_zoom: int, infile: str, outdir: str):
    '''Converts GeoPDF into tileset folder'''
    infile_split = os.path.splitext(infile)

    # get output path if not specified
    if outdir == '__auto__':
        outdir = infile_split[0]

    # make sure the output path is not an existing file
    if os.path.isfile(outdir):
        print('Error: Output directory', outdir, 'is a file.')

    # rasterize and generate tiles
    else:

        # analyze the input file
        analysis = analyze(infile, dpi=dpi, max_zoom=max_zoom)

        # rasterize the PDF file
        if analysis['format'] == 'PDF/Geospatial PDF':
            infile = rasterize(analysis, infile, '%s.tiff' % infile_split[0])

            # tile the TIFF file
            tile(analysis, infile, outdir, min_zoom, max_zoom)

        else:
            print('Error: Input file', infile, 'is not in GeoPDF format.')

@click.command()
@click.option('--info', default=False, is_flag=True, help='Show file information in tab-delimited format')
@click.argument('FILES', nargs=-1)
def batch(info: bool, files):
    '''Batch conversion of GeoPDF files into tilesets'''

    if len(files) > 0:

        if info:
            print(
                'Filename',
                'Format',
                'Map Type',
                'Resolution',
                'Rasterized Size',
                'Zoom Levels',
                sep='\t')

        # analyze each file
        analyses = map(analyze, files)

        # process each file that is a GeoPDF
        for analysis in analyses:
            if info:
                print(
                    analysis['filename'],
                    analysis['format'],
                    analysis['knownType'] if analysis['knownType'] else 'Unknown',
                    '%d dpi' % analysis['dpi'],
                    tuple(analysis['size']),
                    '%d-%d' % (analysis['minZoom'], analysis['maxZoom']),
                    sep='\t')
            elif analysis['format'] == 'PDF/Geospatial PDF':
                    infile = analysis['filename']
                    outdir = os.path.splitext(infile)[0]
                    temptiff = '%s.tiff' % outdir
                    rasterize(analysis, infile, temptiff)
                    tile(analysis, temptiff, outdir)
            else:
                print('Warning: Skipping input file', analysis['filename'], 'not in GeoPDF format.')

    else:
        print("Error: No GeoPDF files specified.")

# main entry point
if __name__ == '__main__':
    cli.add_command(info)
    cli.add_command(tiff)
    cli.add_command(tileset)
    cli.add_command(batch)
    cli()