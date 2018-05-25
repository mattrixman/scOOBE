import unittest
from scoobe.device import get_connected_device
from test.device_common import test_get_set_target

import IPython
def undebug():
    def noop():
        pass
    IPython.embed = noop

class MiniTest(unittest.TestCase):

#    @unittest.skip("modifies device--not part of main run")
    def test_get_set_target(self):

        d = get_connected_device()
        if d.get_info()['marketing_name'] == 'Mini':
            test_get_set_target(d, self)
        else:
            print("Skipped because connected device is not a Mini")
        d.wait_ready()
