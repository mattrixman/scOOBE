from uiautomator import device as ui
from collections import namedtuple
from argparse import ArgumentParser
import xml.etree.ElementTree as ET
import re

def press():
    parser = ArgumentParser()
    parser.add_argument("button_text", type=str)
    args = parser.parse_args()

    ui.screen.on()
    ui(text=args.button_text).click()
