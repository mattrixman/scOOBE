import xml.etree.ElementTree as ET
import re
import sys
import itertools
from time import sleep
from uiautomator import device as ui
from collections import namedtuple
from argparse import ArgumentParser
from sh import adb, egrep, ErrorReturnCode

def has_text(text):
    try:
        egrep(adb.shell(['uiautomator dump /dev/tty']), ".*" + text + ".*")
        return True
    except ErrorReturnCode:
        pass
    return False

def wait_text():
    parser = ArgumentParser()
    parser.add_argument("text", type=str, help="wait for this to appear on the screen (examines xml UI dump)")
    args = parser.parse_args()

    if not has_text(args.text):
        print('waiting for "{}" '.format(args.text), end='')
        spinner = itertools.cycle(['-', '\\', '|', '/'])
        while not has_text(args.text):
            sys.stdout.write(next(spinner))
            sys.stdout.flush()
            sleep(1)
            sys.stdout.write('\b')
            sys.stdout.flush()
        sleep(1)
        print(' ... found')

def press():
    parser = ArgumentParser()
    parser.add_argument("button_text", type=str, help="Press the button that shows this text")
    args = parser.parse_args()

    ui.screen.on()
    ui(text=args.button_text).click()
