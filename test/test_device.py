import unittest
import re
import sh
import scoobe
from scoobe import get_connected_device

import IPython
def undebug():
    def noop():
        pass
    IPython.embed = noop

class DeviceTest(unittest.TestCase):

    def setUp(self):
        self.assertTrue(re.match('^C[A-Z0-9]{3}[UE][CQNOPRD]\d{8}$', get_connected_device().serial))

    def test_adb_available(self):
        self.assertTrue(sh.which("adb") != None)

    def test_clover_device_attached(self):
        self.assertTrue(get_connected_device().codename in scoobe.device.codename2class.keys())
        self.assertTrue(get_connected_device().codename in scoobe.device.prefix2codename.values())
