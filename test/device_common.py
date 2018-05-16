from time import sleep
from collections import namedtuple
import scoobe

Reality = namedtuple('Reality', 'expected actual')

def set_and_assert(device, name, host):

    # make the change
    print("setting target:  {}".format((name, host)))
    device.set_target(name, host)

    (new_name, new_host) = device.get_target()
    print("got target: ", (name, host))
    return Reality((name, host), (new_name, new_host))

def test_get_set_target(device, tester):

    # how is this device configured?
    (orig_name, orig_host) = device.get_target()

    # make a change
    set_test = set_and_assert(device, 'local', 'foo')

    # restore originals
    restore_test = set_and_assert(device, orig_name, orig_host)

    # let the tester know how both went
    tester.assertEqual(set_test.expected, set_test.actual, msg='set_target should stick')
    tester.assertEqual(restore_test.expected, restore_test.actual, msg='we should put it back like we found it')
