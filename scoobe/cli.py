import textwrap
import os
import re
import sys
import json
from collections import namedtuple
from argparse import ArgumentParser, RawTextHelpFormatter, FileType
from abc import ABC, abstractmethod
from enum import Enum
from scoobe.ssh import SshConfig
from scoobe.properties import LocalServer
from scoobe.common import StatusPrinter, Indent

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

def throw_if_not_id_or_uuid(value):
    try:
        if not re.match(r'[A-Za-z0-9]{13}', value):
            reseller_id = int(value)
            assert reseller_id < 100000000000
    except ValueError as err:
        raise ValueError("{} doesn't look like a row id or UUID".format(value))

class Serial(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the device serial number")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))

        if not re.match(r'C[A-Za-z0-9]{3}[UEL][CQNOPRD][0-9]{8}', value):
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

class PlanGroup(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the id or the uuid of the plan group")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        throw_if_not_id_or_uuid(value)
        return value

class Name(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="A name for this thing")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        return value

class TrialDays(_IParsable):

    def preparse(self, parser):
        parser.add_argument('-t', '--'+field_name(self), type=int, default=0, help="how many days should the trial be? (omit for no trial)")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        if value < 0:
            raise ValueError("{} is an invalid trial period".format(value))
        if value == 0:
            value = None
        return value

class EnforcePlanAssignment(_IParsable):

    def preparse(self, parser):
        parser.add_argument('-e', '--'+field_name(self), action='store_true', help="indicates that merchants cannot move between plans on this group")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        return value

class Reseller(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the id or the uuid of the reseller")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        throw_if_not_id_or_uuid(value)
        return value

class Merchant(_IParsable):
    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the id or the uuid of the merchant")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        throw_if_not_id_or_uuid(value)
        return value

class PlanGroup(_IParsable):
    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the id or the uuid of the plan_group")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        throw_if_not_id_or_uuid(value)
        return value

class Plan(_IParsable):
    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the id or the uuid of the plan")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        throw_if_not_id_or_uuid(value)
        return value

class Cpuid(_IParsable):

    def preparse(self, parser):
        parser.add_argument(field_name(self), type=str, help="the device cpu id")

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        if not re.match(r'[A-Fa-f0-9]{16,32}', value):
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

class PlanDict(_IParsable):

    def preparse(self, parser):
        parser.add_argument('-j', '--'+field_name(self), default=sys.stdin, type= FileType('r'), nargs='?',
                            help=textwrap.dedent(
                                """
                                A file containing JSON which definines the plan to stdin.
                                If not specified, will try to read from stdin.
                                If the id and uuid entries are missing, a new plan will be created.
                                If they match, the existing one will be updated.

                                Note that you may need to modify the json for referential integrity, like so:

                                get_plan 3 stg1 \\
                                    | jq 'del(.id)
                                              | del(.uuid)
                                              | .merchant_plan_group="THEMERCHPLANGROUPUUID"
                                              | .app_bundle="THEAPPBUNDLEUUID"' \\
                                    | set_plan stg3
                                 """))

    def get_val(self, parser):
        value = getattr(parser, field_name(self))
        parsed = json.loads(value.read())
        return parsed


class Parsable(Enum):
    serial = Serial
    target = Target
    code = Code
    cpuid = Cpuid
    merchant = Merchant
    plan_group = PlanGroup
    plan = Plan
    reseller = Reseller
    target_type = TargetType
    server = Server
    trial_days = TrialDays
    enforce_plan_assignment = EnforcePlanAssignment
    plan_dict=PlanDict
    name = Name

# given a list of parsables, return a namedtuple containing their results
def parse(*parsables, description=None):

    argparseargs = { 'formatter_class' : RawTextHelpFormatter }

    if description:
        argparseargs['description'] = description

    parser = ArgumentParser(**argparseargs)

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

def clistring():
    snac = os.path.basename(sys.argv[0])
    rest = ' '.join(sys.argv[1:])
    return snac + ' ' + rest

def print_or_warn(string, max_length=500, printer=StatusPrinter()):

    if len(string) > max_length and sys.stdout.isatty():

        validJson = False
        try:
            json.loads(string)
            validJson = True
        except ValueError:
            pass

        if validJson:
            printer("Output is {} chars (json) and stdout is a tty.".format(len(string)))
        else:
            printer("Output is {} chars and stdout is a tty.".format(len(string)))

        with Indent(printer):
            printer("\nIf you really want that much garbage in your terminal, write to a pipe, like so:")
            with Indent(printer):
                printer(clistring() + " | cat")
            if validJson:
                printer("Or better yet, use `jq` to query it:") # because humans shouldn't have to read non-pretty json
                with Indent(printer):
                    printer(clistring() + " | jq '.someKey[3]'")
        sys.exit(15)
    else:
        print(string)
