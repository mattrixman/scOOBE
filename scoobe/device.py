import re
import itertools
import sys
import os
import sh
import json
import ifaddr
import ipaddress
from scoobe.common import StatusPrinter, Indent
from scoobe.cli import parse, Parseable
from collections import namedtuple
from sortedcontainers import SortedDict
from enum import Enum
from itertools import product as cross_product
from sh import adb, sed, sort, grep, egrep, sleep, head, ping, rm
from datetime import datetime

def print_info():
    printer = StatusPrinter(indent=0)
    printer("Getting device info")
    with Indent(printer):
        info = json.dumps(get_connected_device(printer=printer).get_info())
    print(info)

def print_serial():
    printer = StatusPrinter(indent=0)
    printer("Getting device serial")
    with Indent(printer):
        serial = get_connected_device(printer=printer).serial
    print(serial)

def print_cpuid():
    printer = StatusPrinter(indent=0)
    printer("Getting device cpuid")
    with Indent(printer):
        cpuid = get_connected_device().cpuid
    print(cpuid)

def ready():
    try:
        if str(adb.shell(['getprop', 'sys.boot_completed'])).strip() == '1':
            return True
            return False
    except sh.ErrorReturnCode:
        return False

def wait_ready(printer=StatusPrinter()):
    if not ready():
        printer('waiting for device ', end='')
        spinner = itertools.cycle(['-', '\\', '|', '/'])
        while not ready():
            sys.stdout.write(next(spinner))
            sys.stdout.flush()
            sleep(1)
            sys.stdout.write('\b')
            sys.stdout.flush()
        sleep(1)
        printer(' ... ready')

def master_clear():
    printer = StatusPrinter(indent=0)
    printer("Clearing Device")
    with Indent(printer):
        with Indent(printer):
            d = get_connected_device(printer=printer)
        cmd = ['shell', 'am', 'broadcast', '-a', 'android.intent.action.MASTER_CLEAR', '-n', 'android/com.android.server.MasterClearReceiver']
        printer('\'' + ' '.join(cmd) + '\'')
        adb(cmd)
    sleep(d.get_shutdown_delay())

def set_target():
    parsed_args = parse(Parseable.target_type, Parseable.server)

    printer = StatusPrinter(indent=0)
    printer("Targeting attached device to {} {}".format(parsed_args.targettype, parsed_args.server))
    with Indent(printer):
        get_connected_device(printer=printer).set_target(parsed_args.targettype, parsed_args.server)

# Station 2018, Mini2 and Flex have a clover_cpuid (16 characters)
# in addition to the 32 digit cpuid
# if the device has a clover_cpuid get that
# otherwise fall back to the 32 digit cpuid
# Station 2018 returns two cpuids, one of which is all 0's
# Flex and Mini return just one
# This takes the highest (string order) which works for both
def get_cpuid(codename):
    if codename in ["KNOTTY_PINE","GOLDEN_OAK","BAYLEAF"]:
        return  sorted(list(sed(adb.shell('getprop'), '-n',
                r's/^.*clover_cpuid.*\[\([0-9a-fA-F]\{16\}\).*$/\1/p')))[-1].strip()
    else:
        return  sorted(list(sed(adb.shell('getprop'), '-n',
                r's/^.*cpuid.*\[\([0-9a-fA-F]\{32\}\).*$/\1/p')))[-1].strip()

def get_connected_device(printer=StatusPrinter()):
    wait_ready(printer)

    # tested for flex, mini, and station_2018
    serial = str(sed(adb.shell('getprop'), '-n',
        r's/^.*serial.*\[\(C[A-Za-z0-9]\{3\}[UEL][CQNOPRD][0-9]\{8\}\).*$/\1/p')).split('\n')[0]
    assert(len(serial) > 0)

    codename = prefix2codename[serial[2:4]]

    device = codename2class[codename]()

    cpuid = get_cpuid(codename)
    assert(len(cpuid) > 0)

    device.serial = serial
    device.cpuid = cpuid
    device.codename = codename

    printer("Found attached device: " + str(device))

    return device

def screenshot(device, printer=StatusPrinter()):
    printer("Dumping screenshot for Device: {}".format(device.serial))
    with Indent(printer):

        # make way for new file
        outfile_name = "{}_{}.png".format(device.serial,
                                          datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        outfile_path = os.path.join(os.getcwd(), outfile_name)
        rm('-f', outfile_path)

        # get the screencap
        tempfile_path = '/sdcard/{}'.format(outfile_name)
        adb.shell('screencap', '-p', tempfile_path)
        adb.pull(tempfile_path)
        adb.shell('rm', tempfile_path)

        printer("Wrote " + outfile_path)

def print_screenshot():
    parsed_args = parse(description="Dump the current screen of the connected device to a png file")
    printer = StatusPrinter(indent=0)

    device = get_connected_device(printer=printer)
    screenshot(device, printer=printer)

# base class for devices
class Device:

    # if we told the device to reboot, what is tha maximum time that will elapse before the adb connection goes away?
    # (so we can start waiting for it to come back)
    def get_shutdown_delay(self):
        return 8

    def get_info(self):
        target = ':'.join(self.get_target()) # target:url
        return {"marketing_name":self.__class__.__name__,
                "code_name":self.codename,
                "serial":self.serial,
                "cpuid":self.cpuid,
                "targeting":target}

    def set_target(self, target, url, printer=StatusPrinter()):
        self.wait_ready()

        if re.match('http://.*', url):
            url = url[7:]

        printer("Targeting device to: " + url)
        with Indent(printer):

            cmd = ['su', '1000', 'content', 'call', '--uri', 'content://com.clover.service.provider',
                '--method', 'changeTarget', '--extra', 'target:s:{}:{}'.format(target, url)]

            printer('\'' + ' '.join(cmd) + '\'')
            adb.shell(cmd)

        # the above call causes a reset
        # wait until the adb connection is lost
        printer("Waiting {} seconds for device to begin reboot..."
                .format(self.get_shutdown_delay()))
        sleep(self.get_shutdown_delay())

    def wait_ready(self):
        # TODO: multiple connected devices
        wait_ready()

    def __str__(self):
        return "{} ({}) [{}]".format(self.codename, self.__class__.__name__, self.serial)

# device specific classes

class Mini(Device) :

    def get_target(self):
        self.wait_ready()
        target_url = str(sed(adb.shell('mmc_access', 'r_yj3_target'), '-n',
                r's/^.*YJ3[^:]*: \([^:]*\):\(.*\).*$/\1,\2/p')).strip()
        assert(len(target_url) > 0)
        (target, url) = target_url.split(',')
        return (target, url)

class Mini2(Device):

    def get_target(self):
        self.wait_ready()
        target = str(adb.shell('cat', '/pip/CLOVER_TARGET'))
        url = str(adb.shell('cat', '/pip/CLOVER_CLOUD_URL'))
        if re.match('http://.*', url):
            url = url[7:]
        return (target, url)

class Flex(Device):

    def get_shutdown_delay(self):
        return 16

    def get_target(self):
        self.wait_ready()
        target = str(adb.shell('cat', '/pip/CLOVER_TARGET'))
        url = str(adb.shell('cat', '/pip/CLOVER_CLOUD_URL'))
        if re.match('http://.*', url):
            url = url[7:]
        return (target, url)

class Mobile(Device):

    def get_target(self):
        self.wait_ready()
        target_url = str(sed(adb.shell('mmc_access', 'r_yj2_target'), '-n',
                r's/^.*YJ2[^:]*: \([^:]*\):\(.*\).*$/\1,\2/p')).strip()
        assert(len(target_url) > 0)
        (target, url) = target_url.split(',')
        return (target, url)

class Station(Device):
    pass

class Station2018(Device):

    def get_target(self):
        self.wait_ready()
        target = str(adb.shell('cat', '/pip/CLOVER_TARGET'))
        url = str(adb.shell('cat', '/pip/CLOVER_CLOUD_URL'))
        if re.match('http://.*', url):
            url = url[7:]
        return (target, url)

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
                   "KNOTTY_PINE" : Mini2,
                   "BAYLEAF"     : Flex,
                   "GOLDEN_OAK"  : Station2018 }

def get_local_remote_ip(printer=StatusPrinter()):

    printer("Probing Network From Both Sides")

    Address = namedtuple("Address",  "ip_str int")

    def read_ip(msg, ip_str, printer):
        if '127.0.0.1' not in ip_str:
            printer("{:>10}:  {}".format(msg, ip_str))
            return Address(ip_str, int(ipaddress.IPv4Address(ip_str)))
        else:
            return None

    # get all ipv4 addresses among the local network adapters
    printer("Local Addresses:")
    local_addresses = set()
    with Indent(printer):
        adapters = ifaddr.get_adapters()
        for adapter in adapters:
            for ip in adapter.ips:
                ip_str = str(ip.ip)
                if re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$', ip_str):
                    address = read_ip(adapter.nice_name, ip_str, printer)
                    if address is not None:
                        local_addresses.add(address)
        printer('')

    # get all ipv4 addresses among the device's known routes
    printer("Device Address Candidates:")
    device_addresses = set()
    with Indent(printer):
        # keep only things that look like ip addresses
        device_ip_strs = set(re.findall(r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+',
            str(
                sed(
                    # TODO: this would be cleaner with 'adb shell netcfg' which I discovered too late

                    # dump the routing table
                    adb(['shell', 'ip', 'route']),

                    # print only lines containing 'src', and only the part after the 'src'
                    ['-n', r's#^.*src\(.*\)$#\1#p']
                    )
                ).strip()))

        for ip_str in device_ip_strs:
            address = read_ip("route entry",  ip_str, printer)
            if address is not None:
                device_addresses.add(address)
        printer('')

    # In an ip address, the more significant bits are subnet bits, less significant ones are network bits
    # XOR will give subnet zeros when two ip addresses are in the same subnet. Therefore, smaller distances
    # returned by this function indicate that the addresses are more likely to be able to talk to each other
    def subnet_distance(ip_a, ip_b):
        return ip_a.int ^ ip_b.int

    # Ping local from remote, and ping remote from local
    # Return true if both succeed
    def can_talk(local, remote, printer):

        printer("Pinging {} -> {}".format(remote, local))
        with Indent(printer):
            printer('''adb shell 'ping -c 4 {} && echo SUCCESS || echo FAIL' '''.format(local))
            with Indent(printer):
                remote2local = str(adb(['shell', 'ping -c 4 {} && echo SUCCESS || echo FAIL'.format(local)]))
                printer(remote2local)

        if 'SUCCESS' in remote2local:
            printer("Pinging {} -> {}".format(local, remote))
            with Indent(printer):
                printer('ping -c 4 {}'.format(local))
                with Indent(printer):
                    try:
                        local2remote = ping(['-c', '4', remote])
                    except sh.ErrorReturnCode as err:
                        local2remote = err
                    printer(local2remote)

            if local2remote.exit_code == 0:
                return True
        return False

    # sort local/remote pairs by distance
    matches = SortedDict()
    for local_ip, remote_ip in cross_product(local_addresses, device_addresses):
        matches[subnet_distance(local_ip, remote_ip)] = (local_ip.ip_str, remote_ip.ip_str)

    # check connectivity (nearest first)
    for local, remote in matches.values():
        if can_talk(local, remote, printer):
            return (local, remote)

def probe_network(selector=lambda x : x, printer=StatusPrinter()):

    with Indent(printer):
        local_remote = get_local_remote_ip()

    if local_remote:
        return selector({ "local_ip" : local_remote[0],
                   "device_ip" : local_remote[1] })
    else:
        printer("No connectivity between local machine and device")
        sys.exit(40)

def print_probe_network():

    printer = StatusPrinter(indent=0)
    print(probe_network(), printer=printer)

def print_device_ip():

    printer = StatusPrinter(indent=0)
    printer("Seeking accessable device IP")

    with Indent(printer):
        device_ip = probe_network(selector = lambda x : x['device_ip'], printer=printer)
    print(device_ip)

def print_local_ip():

    printer = StatusPrinter(indent=0)
    printer("Seeking local IP accessable by device")

    with Indent(printer):
        local_ip = probe_network(selector = lambda x : x['local_ip'], printer=printer)
    print(local_ip)

def print_device_packages():

    listing = str(grep(egrep(adb(['shell', 'dumpsys', 'package', '*']), r'Package..com\.clover|versionName'), ['Package', '-A1']))
    package_names = re.findall(r'Package \[(.*)\].*', listing)
    versions = list(map(lambda x : x.strip(), re.findall(r'versionName=(.*)', listing)))
    package2version = {}
    for p, v in zip(package_names, versions):
        package2version[p] = v
    print(json.dumps(package2version, indent=4))
