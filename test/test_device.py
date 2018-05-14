import unittest
import re
import sh
from scoobe import Device

#import IPython

class DeviceTest(unittest.TestCase):

    def test_adb_available(self):
        self.assertTrue(sh.which("adb") != None)

    def test_adb_can_see_device(self):
        self.assertTrue(any(re.match('^C.*device$', line) for line in sh.adb('devices').split('\n')))

    def test_get_serial(self):
        self.assertTrue(re.match('^C[A-Z0-9]{3}[UE][CQNOPRD]\d{8}$', Device().serial))

    def test_clover_device_attached(self):
        self.assertTrue(Device().type in Device.prefix2device.values())

    def test_Device_class_referencable(self):
        self.assertTrue('GOLDLEAF' in Device.prefix2device.values())
