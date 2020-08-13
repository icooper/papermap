#!/usr/bin/env python

import pyximport; pyximport.install()
import click
import random

from typing import List, Dict
from time import sleep
from PIL import Image, ImageDraw, ImageFont
from it8951.constants import DisplayModes, PixelModes
from it8951.display import AutoEPDDisplay

def get_display(context):
    print('Connecting to panel...')
    vcom = context.obj['vcom']
    bus = context.obj['bus']
    device = context.obj['device']
    spi_mhz = context.obj['spi_mhz']
    rotate = context.obj['rotate']
    display = AutoEPDDisplay(vcom = -abs(vcom), bus=bus, device=device, spi_hz=spi_mhz * 10**6, rotate=rotate)
    print('...connection successful')
    if context.obj['clear']:
        display.clear()
    return display

def draw_text(display, text, font):
    w_img, h_img = display.frame_buf.size
    w_text, h_text = font.getsize(text)
    ImageDraw.Draw(display.frame_buf).text(((w_img - w_text) // 2, (h_img - h_text) // 2), text, font=font)

def draw_noise(display, size, continuous):
    width, height = display.frame_buf.size
    levels = 4 if continuous else 16
    for x in range(0, width, size):
        for y in range(0, height, size):
            color = (random.randrange(0, levels) * (32 // (levels - 1))) * 8
            box = (x, y, x + size, y + size)
            display.frame_buf.paste(color, box)

@click.group()
@click.option('--debug', default=False, is_flag=True, help='Show extra messages')
@click.option('--vcom', default=-1.43, help='Specify panel VCOM', show_default=True)
@click.option('--bus', default=0, help='Specify SPI bus', show_default=True)
@click.option('--device', default=0, help='Specify SPI device', show_default=True)
@click.option('--spi_mhz', default=24, help='Specify SPI transfer speed (in MHz)', show_default=True)
@click.option('--rotate', default=None, type=click.Choice(['CW', 'CCW', 'flip']), help='Rotate the image on the panel')
@click.option('--noclear', default=False, is_flag=True, help='Do not clear the panel first')
@click.pass_context
def cli(context, debug:bool, vcom: float, bus: int, device: int, spi_mhz: int, rotate: str, noclear: bool):
    context.ensure_object(dict)
    context.obj['debug'] = debug
    context.obj['vcom'] = vcom
    context.obj['bus'] = bus
    context.obj['device'] = device
    context.obj['spi_mhz'] = spi_mhz
    context.obj['rotate'] = rotate
    context.obj['clear'] = not noclear

@click.command(name='info')
@click.pass_context
def panel_info(context):
    """Show panel information"""
    context.obj['clear'] = False # don't automatically clear the panel
    display = get_display(context)
    print('Panel information:')
    print('  size = %dx%d' % (display.epd.width, display.epd.height))
    print('  img buffer address: 0x%08x' % display.epd.img_buf_address)
    print('  firmware = %s' % display.epd.firmware_version)
    print('  LUT = %s' % display.epd.lut_version)

@click.command(name='clear')
@click.pass_context
def clear_display(context):
    """Clear the panel"""
    context.obj['clear'] = False # don't automatically clear the panel
    display = get_display(context)
    display.clear()

@click.command(name='gradient')
@click.option('--levels', default=16, help='Number of levels in the gradient')
@click.pass_context
def show_gradient(context, levels: int):
    """Show a gradient across the panel"""

    # validate the steps parameter
    if levels < 2 or levels > 256:
        print('gradient: levels must be within the range [2..256]')

    else:
        # connect to the display
        display = get_display(context)
        
        # draw a gradient across the panel framebuffer
        for i in range(levels):

            # get the color
            color = i * (256 // levels)

            # get the outline of the box
            box = (
                i * display.width // levels,        # xmin
                0,                                  # ymin
                (i + 1) * display.width // levels,  # xmax
                display.height                      # ymax
            )

            # draw the box on the framebuffer
            display.frame_buf.paste(color, box)

        # redraw the image on the panel
        display.draw_full(DisplayModes.GC16)

@click.command(name='noise')
@click.option('--size', default=72, help='Size of the generated noise pixels')
@click.option('--continuous', default=False, is_flag=True, help='Continuously update panel')
@click.pass_context
def show_noise(context, size: int, continuous: bool):
    """Show randomly-generated noise on the panel"""

    # validate the options
    if size < 1 or size > 1000:
        print('noise: size must be within the range [1..1000]')

    else:
        display = get_display(context)
        
        while True:
            draw_noise(display, size, continuous)
            display.draw_full(DisplayModes.DU4 if continuous else DisplayModes.GC16)
            if not continuous:
                break

@click.command(name='text')
@click.option('--fontfile', default='/usr/share/fonts/truetype/piboto/Piboto-Regular.ttf', help='Path to TrueType font file')
@click.option('--size', default=120, help='Font size')
@click.option('--mode', default='DU4', type=click.Choice(['A2', 'DU', 'DU4', 'GC16']), help='Rotate the image on the panel')
@click.argument('text', default='Hello, World!')
@click.pass_context
def show_text(context, fontfile: str, size: int, mode: str, text: str):
    """Display text on the panel"""

    # set up our display modes
    displayModes = {
        'A2': DisplayModes.A2,
        'DU': DisplayModes.DU,
        'DU4': DisplayModes.DU4,
        'GC16': DisplayModes.GC16
    }
    displayMode = displayModes[mode]

    context.obj['clear'] = True # so we start with a white panel
    display = get_display(context)

    # load the font
    font = ImageFont.truetype(fontfile, size)

    # draw the text
    for i in range(0, 10):
        draw_text(display, str(10 - i), font)
        display.draw_partial(displayMode)
        display.frame_buf.paste(0xFF, (0, 0, display.width, display.height))

    draw_text(display, text, font)
    display.draw_partial(displayMode)

@click.command(name='wipe')
@click.option('--size', default=36, help='Step size')
@click.pass_context
def show_wipe(context, size: int):
    """Wipe the screen to get rid of any ghosting"""
    #context.obj['clear'] = False # don't clear the screen first
    display = get_display(context)
    width, height = display.frame_buf.size
    display.frame_buf.paste(0x00, (0, 0, width, height))

    # wipe white
    for i in range(0, width, size):
        box = (
            i,          # xmin
            0,          # ymin
            i + size,   # xmax
            height      # ymax
        )
        print('white', i, box)
        display.frame_buf.paste(0xFF, box)
        display.draw_partial(DisplayModes.DU4)

    # wipe black
    for i in range(0, width, size):
        box = (
            i,          # xmin
            0,          # ymin
            i + size,   # xmax
            height      # ymax
        )
        print('black', i, box)
        display.frame_buf.paste(0x00, box)
        display.draw_partial(DisplayModes.DU4)

    # wipe white
    for i in range(0, width, size):
        box = (
            i,          # xmin
            0,          # ymin
            i + size,   # xmax
            height      # ymax
        )
        print('white', i, box)
        display.frame_buf.paste(0xFF, box)
        display.draw_partial(DisplayModes.DU4)

if __name__ == '__main__':
    cli.add_command(panel_info)
    cli.add_command(clear_display)
    cli.add_command(show_gradient)
    cli.add_command(show_noise)
    cli.add_command(show_text)
    cli.add_command(show_wipe)
    cli()