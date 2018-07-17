import textwrap
import os
import re
from collections import namedtuple
from argparse import ArgumentParser, RawTextHelpFormatter
from abc import ABC, abstractmethod
from enum import Enum
from scoobe.ssh import SshConfig
from scoobe.properties import LocalServer

# used when generating classes (namedtuples) to store results
def container_name_component(obj):
    return type(obj).__name__

# used when generating classes (namedtuples) to store results
def field_name(obj):
    return type(obj).__name__.lower()


# an abstract class for things we want from the command line
class _IParsable(ABC):

    def __init__(self):
        super().__init__()


    # configure argparse
    @abstractmethod
    def preparse(self, parser):
        pass

    # validate/generate result
    @abstractmethod
    def get_val(self, parser):
        pass

class Serial(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the device serial number")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))

        if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', value):
           raise ValueError("{} doesn't look like a serial number".format(value))
        return value

class Target(_IParsable):

    def preparse(self, parser):
        parser.add_argument("target", type=str, help=textwrap.dedent('''\
                if server is remote:
                    the ssh host of server (specified in ~/.ssh/config)
                if server is local:
                    the path to its *.properties file
                '''))

    def get_val(self, parser):

       value = getattr(parser, field_name(self))
       if os.path.exists(value):
            return LocalServer(value)
       else:
            return SshConfig(value)

class Code(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=int, help="the desired activation code")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        if not re.match(r'[0-9]{8}', str(value)):
           raise ValueError("{} doesn't look like an activation code".format(value))
        return value

class Reseller(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=int, help="the reseller id")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        if not value >= 0:
            raise ValueError("{} doesn't look like a reseller_id".format(value))
        return value

class Merchant(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the uuid of the merchant")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        if not re.match(r'[A-Za-z0-9]{13}', value):
           raise ValueError("{} doesn't look like a merchant UUID".format(value))
        return value

class Cpuid(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the device cpu id")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        if not re.match(r'[A-Fa-f0-9]{32}', value):
           raise ValueError("{} doesn't look like a device cpuid".format(value))
        return value

class CloudTarget(Enum):
    prod_us = 'prod_us'
    prod_eu = 'prod_eu'
    dev = 'dev'
    local = 'local'

    def __str__(self):
        return self.value

class TargetType(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=CloudTarget, choices=list(CloudTarget))

    def get_val(self, parser):
        return getattr(parser, field_name(self)).value

class Server(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help=\
                textwrap.dedent(
                '''
                An IP Address (ex: 192.168.1.2)
                or the hostname of a clover server (ex: dev1.dev.clover.com)
                '''))

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        if "clover.com" in value:
            return value
        if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(:[0-9]*)?$', value):
           raise ValueError("{} doesn't look like an ip address".format(value))
        return value

class Parsable(Enum):
    serial = Serial
    target = Target
    code = Code
    cpuid = Cpuid
    merchant = Merchant
    reseller = Reseller
    target_type = TargetType
    server = Server

# given a list of parsables, return a namedtuple containing their results
def parse(*parsables):

    parser = ArgumentParser(formatter_class=RawTextHelpFormatter)

    # replace enums with underlying classes
    parsables = [ x.value() for x in parsables ]

    container_name = ""
    field_list = ""
    for parsable in parsables:

        # gather names
        container_name += container_name_component(parsable)
        field_list += " " + field_name(parsable)

        # prepare the parser
        parsable.preparse(parser)

    # remove leading space
    field_list.strip()

    # parse from the command line
    parsed = parser.parse_args()

    # prepare results
    results = []
    for parsable in parsables:
        results.append(parsable.get_val(parsed))

    # wrap and return them
    ContainerType = namedtuple(container_name, field_list)
    return ContainerType(*results)
