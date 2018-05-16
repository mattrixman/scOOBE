import re
import itertools
import sys
import sh
from sh import adb
from sh import sed
from sh import egrep
from time import sleep

def info():
    print(get_connected_device().get_info())

def ready():
    try:
        if str(adb.shell(['getprop', 'sys.boot_completed'])).strip() == '1':
            return True
        else:
            return False
    except sh.ErrorReturnCode:
        return False

def wait_ready():
    if not ready():
        print('waiting for device ', end='')
        spinner = itertools.cycle(['-', '\\', '|', '/'])
        while not ready():
            sys.stdout.write(next(spinner))
            sys.stdout.flush()
            sleep(1)
            sys.stdout.write('\b')
            sys.stdout.flush()
        sleep(1)
        print(' ... ready')

def get_connected_device():
    wait_ready()

    # tested for flex and mini
    serial = str(sed(adb.shell('getprop'), '-n',
        r's/^.*serial.*\[\(C[A-Za-z0-9]\{3\}[UE][CQNOPRD][0-9]\{8\}\).*$/\1/p')).split('\n')[0]
    assert(len(serial) > 0)

    # tested for flex and mini
    cpuid = str(sed(adb.shell('getprop'), '-n',
        r's/^.*cpuid.*\[\([0-9a-fA-F]\{32\}\).*$/\1/p')).split('\n')[0]
    assert(len(cpuid) > 0)

    codename = prefix2codename[serial[2:4]]

    device = codename2class[codename]()
    device.serial = serial
    device.cpuid = cpuid
    device.codename = codename
    return device

# base class for devices
class Device:

    # if we told the device to reboot, what is tha maximum time that will elapse before the adb connection goes away?
    # (so we can start waiting for it to come back)
    def get_shutdown_delay(self):
        return 8

    def get_info(self):
        target = ':'.join(self.get_target()) # name:host
        return {"marketing_name":self.__class__.__name__,
                "code_name":self.codename,
                "serial":self.serial,
                "cpuid":self.cpuid,
                "targeting":target}

    def set_target(self, name, host):
        self.wait_ready()

        if re.match('http://.*', host):
            host = host[7:]

        print("targeting device to: " + host)

        cmd = ['su', '1000', 'content', 'call', '--uri', 'content://com.clover.service.provider',
            '--method', 'changeTarget', '--extra', 'target:s:{}:{}'.format(name, host)]

        # print(' '.join(cmd))
        adb.shell(cmd)

        # the above call causes a reset
        # wait until the adb connection is lost
        sleep(self.get_shutdown_delay())

    def wait_ready(self):
        # TODO: multiple connected devices
        wait_ready()

# device specific classes

class Mini(Device) :

    def get_target(self):
        self.wait_ready()
        name_host = str(sed(adb.shell('mmc_access', 'r_yj3_target'), '-n',
                r's/^.*YJ3[^:]*: \([^:]*\):\(.*\).*$/\1,\2/p')).strip()
        assert(len(name_host) > 0)
        (name, host) = name_host.split(',')
        return (name, host)

class Flex(Device):

    def get_shutdown_delay(self):
        return 16

    def get_target(self):
        self.wait_ready()
        name = str(adb.shell('cat', '/pip/CLOVER_TARGET'))
        url = str(adb.shell('cat', '/pip/CLOVER_CLOUD_URL'))
        if re.match('http://.*', url):
            url = url[7:]
        return (name, url)

class Mobile(Device):
    pass

class Station(Device):
    pass

class Station2018(Device):
    pass

# use digits 2-4 of serial to identify device
# https://confluence.dev.clover.com/display/ENG/How+to+decipher+a+Clover+device+serial+number
prefix2codename = { "10" : "GOLDLEAF",
                    "20" : "LEAFCUTTER",
                    "21" : "LEAFCUTTER",
                    "30" : "MAPLECUTTER",
                    "31" : "MAPLECUTTER",
                    "32" : "KNOTTY_PINE",
                    "41" : "BAYLEAF",
                    "42" : "BAYLEAF",
                    "50" : "GOLDEN_OAK" }


codename2class = { "GOLDLEAF"    : Station,
                   "LEAFCUTTER"  : Mobile,
                   "MAPLECUTTER" : Mini,
                   "KNOTTY_PINE" : Mini,
                   "BAYLEAF"     : Flex,
                   "GOLDEN_OAK"  : Station2018 }

