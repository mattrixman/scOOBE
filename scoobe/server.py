import sys
import os
import re
import requests
import json
import textwrap
import argparse
import xml.etree.ElementTree as ET
from collections import namedtuple
from argparse import ArgumentParser
from scoobe.common import StatusPrinter, Indent, print_request, print_response
from scoobe.ssh import SshConfig
from scoobe.mysql import Query
from scoobe.properties import LocalServer

# just a container for functions that grab stuff from the cli
class Arg:

    # lots of copy-paste inheritence in this class
    # TODO: make it better

    target_help_str = textwrap.dedent('''\
            if server is remote:
                the ssh host of server (specified in ~/.ssh/config)
            if server is local:
                the path to its *.properties file
            ''')

    def pick_target(param):
       if os.path.exists(param):
            return LocalServer(param)
       else:
            return SshConfig(param)

    # parse cli args, return one of these:
    SerialTarget = namedtuple('SerialTarget', 'serial_num target')
    def parse_serial_target():
        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("serial_num", type=str, help="the device serial number")
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        args = parser.parse_args()

        if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
           raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

        return Arg.SerialTarget(args.serial_num,
                                Arg.pick_target(args.target))

    # parse cli args, return one of these:
    SerialTargetCode = namedtuple('SerialTarget', 'serial_num target activation_code')
    def parse_serial_target_code():
        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("serial_num", type=str, help="the device serial number")
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        parser.add_argument("activation_code", type=str, help="the desired activation code")
        args = parser.parse_args()

        if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
           raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

        return Arg.SerialTargetCode(args.serial_num,
                                    Arg.pick_target(args.target),
                                    args.activation_code)

    # parse cli args, return one of these:
    SerialTargetReseller = namedtuple('SerialTargetReseller', 'serial_num target reseller_id')
    def parse_serial_target_reseller():

        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("serial_num", type=str, help="the device serial number")
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        parser.add_argument("reseller_id", type=int, help="the reseller id (int)")
        args = parser.parse_args()

        if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
           raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

        if not args.reseller_id >= 0:
           raise ValueError("{} doesn't look like a reseller_id".format(args.reseller_id))

        return SerialTargetReseller(args.serial_num,
                                 Arg.pick_target(args.target),
                                 args.reseller_id)

    # parse cli args, return one of these:
    MerchantTarget = namedtuple('MerchantTarget', 'merchant_uuid target')
    def parse_merchant_target():

        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("merchant_uuid", type=str, help="the uuid of the merchant")
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        args = parser.parse_args()

        if not re.match(r'[A-Za-z0-9]{13}', args.merchant_uuid):
           raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant_uuid))

        return Arg.MerchantTarget(args.merchant_uuid,
                                  Arg.pick_target(args.target))

    # grab the serial number, cpuid, target, and merchant from the command line
    ProvisionArgs = namedtuple('ProvisionArgs', 'serial_num cpuid target merchant')
    def parse_serial_target_merch():
        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("serial_num", type=str, help="the device serial number")
        parser.add_argument("cpuid", type=str, help="the device cpu id")
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        parser.add_argument("merchant", type=str,
                help="UUID of merchant that will be using this device")
        args = parser.parse_args()

        if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
           raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

        if not re.match(r'[A-Za-z0-9]{13}', args.merchant):
           raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant))

        if not re.match(r'[A-Fa-f0-9]{32}', args.cpuid):
           raise ValueError("{} doesn't look like a device cpuid".format(args.cpuid))

        return Arg.ProvisionArgs(args.serial_num,
                                 args.cpuid,
                                 Arg.pick_target(args.target),
                                 args.merchant)

    # grab the serial number, cpuid, target, and merchant from the command line
    ProvisionArgs = namedtuple('ProvisionArgs', 'serial_num cpuid target merchant')
    def parse_serial_target_merch():
        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("serial_num", type=str, help="the device serial number")
        parser.add_argument("cpuid", type=str, help="the device cpu id")
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        parser.add_argument("merchant", type=str,
                help="UUID of merchant that will be using this device")
        args = parser.parse_args()

        if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
           raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

        if not re.match(r'[A-Za-z0-9]{13}', args.merchant):
           raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant))

        if not re.match(r'[A-Fa-f0-9]{32}', args.cpuid):
           raise ValueError("{} doesn't look like a device cpuid".format(args.cpuid))

        return Arg.ProvisionArgs(args.serial_num,
                                 args.cpuid,
                                 Arg.pick_target(args.target),
                                 args.merchant)

    # grab the serial number, cpuid, target, and merchant from the command line
    ProvisionNewArgs = namedtuple('ProvisionArgs', 'serial_num cpuid target merchant reseller')
    def parse_serial_target_merch_reseller():
        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("serial_num", type=str, help="the device serial number")
        parser.add_argument("cpuid", type=str, help="the device cpu id")
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        parser.add_argument("merchant", type=str,
                help="UUID of merchant that will be using this device")
        parser.add_argument("reseller", type=int, help="the reseller to board the new merchant to")
        args = parser.parse_args()

        if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
           raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

        if not re.match(r'[A-Za-z0-9]{13}', args.merchant):
           raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant))

        if not re.match(r'[A-Fa-f0-9]{32}', args.cpuid):
           raise ValueError("{} doesn't look like a device cpuid".format(args.cpuid))

        return Arg.ProvisionArgs(args.serial_num,
                                 args.cpuid,
                                 Arg.pick_target(args.target),
                                 args.merchant,
                                 args.reseller)

    # grab the target from the command line
    Target = namedtuple('TargetArgs', 'target')
    def parse_target():
        parser = ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("target", type=str, help=Arg.target_help_str)
        args = parser.parse_args()

        return Arg.Target(Arg.pick_target(args.target))

def internal_auth(target, printer=StatusPrinter):

    endpoint = '{}://{}/cos/v1/dashboard/internal/login'.format(
                target.get_hypertext_protocol(),
                target.get_hostname() + ":" + target.get_http_port())

    headers = { 'Content-Type' : 'application/json ',
                      'Accept' : 'application/json, text/javascript, */*; q=0.01',
                  'Connection' : 'keep-alive' }

    data = {'username' : 'joe.blow',
            'password' : 'letmein' }

    print_request(printer, endpoint, headers, data)

    response = requests.post(endpoint, data=json.dumps(data))

    print_response(printer, response)

    try:
        return response.headers['set-cookie']
    except KeyError:
        printer("{} has cloverDevAuth unset, TODO: implement user/pass handling and actually authenticate")
        return None

def print_cookie():
    args = Arg.parse_target()
    printer = StatusPrinter(indent=0)

    printer("Getting a login cookie from {}".format(args.target.get_name()))
    with Indent(printer):
        cookie = internal_auth(args.target, printer=printer)

    print(cookie)


Merchant = namedtuple('Merchant', 'id uuid')
def get_merchant(serial_num, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id, uuid
            FROM merchant
            WHERE id = (SELECT merchant_id
                        FROM device_provision
                        WHERE serial_number = '{}');
            """.format(serial_num))

    q.on_empty("this device is not associated with a merchant on {}".format(target.get_name()))

    return q.get_from_first_row(
            lambda row: Merchant(row['id'], row['uuid'].decode('utf-8')),
            printer=printer)

def print_merchant():

    args = Arg.parse_serial_target()
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s merchant according to {}".format(args.serial_num, args.target.get_name()))
        with Indent(printer):
            merchant = get_merchant(args.serial_num, args.target, printer=printer)
        print(json.dumps(merchant._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

# returns the merchant currently associated with the specified device
Reseller = namedtuple('Reseller', 'id uuid name')
def get_device_reseller(serial_num, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id, uuid, name
            FROM reseller
            WHERE id = (SELECT reseller_id
                        FROM device_provision
                        WHERE serial_number = '{}');
            """.format(serial_num))

    q.on_empty("this device is not associated with a reseller according to {}".format(target.get_name()))

    return q.get_from_first_row(
            lambda row: Reseller(row['id'], row['uuid'].decode('utf-8'), row['name'].decode('utf-8')),
            printer=printer)

def print_device_reseller():

    args = Arg.parse_serial_target()
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(args.serial_num, args.target.get_name()))
        with Indent(printer):
            merchant = get_device_reseller(args.serial_num, args.target, printer=printer)
        print(json.dumps(merchant._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(90)


SetResult = namedtuple('SetResult', 'change_made description')
def describe_set_device_reseller(serial_num, target, target_reseller_id, printer=StatusPrinter()):

    printer("Checking the device's reseller")
    with Indent(printer):
        current_reseller = get_device_reseller(serial_num, target, printer)

    # don't modify if desired value is already set
    if int(current_reseller.id) == int(target_reseller_id):
        return SetResult(False, "The device's current reseller is the same as the target reseller ({}), making no change"
                                .format(target_reseller_id))

    # otherwise motfdy
    else:
        printer("Changing the device's reseller: {} -> {}".format(current_reseller.id, target_reseller_id))
        with Indent(printer):

            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE device_provision
                    SET reseller_id = {}
                    WHERE serial_number = '{}';
                    """.format(target_reseller_id, serial_num))

            rows_changed = q.run_get_rows_changed(printer=printer)
            if rows_changed == 1:
                return SetResult(False, "NOTICE: the attached device's reseller has changed from {} to {}".format(
                                        current_reseller.id, target_reseller_id))
            else:
                raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_set_device_reseller():

    args = Arg.parse_serial_target_reseller()
    printer = StatusPrinter(indent=0)

    printer("Setting the device's reseller to {}".format(args.reseller_id))
    with Indent(printer):
        result = describe_set_device_reseller(args.serial_num, args.target, args.reseller_id, printer=printer)
    printer(result.description)

def get_merchant_reseller(merchant_uuid, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id, uuid, name
            FROM reseller
            WHERE id = (SELECT reseller_id
                        FROM merchant
                        WHERE uuid = '{}');
            """.format(merchant_uuid))

    q.on_empty("this device is not associated with a reseller on {}".format(target.get_name()))

    return q.get_from_first_row(
            lambda row: Reseller(row['id'], row['uuid'].decode('utf-8'), row['name'].decode('utf-8')),
            printer=printer)

def print_merchant_reseller():

    args = Arg.parse_serial_target()
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(args.merchant_uuid, args.target.get_name()))
        with Indent(printer):
            reseller = get_merchant_reseller(args.merchant_uuid, args.target, printer=printer)
        print(json.dumps(reseller._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def get_activation_code(target, serial_num, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial_num))

    q.on_empty("This device is not known to {}".format(target.get_name()))

    return int(q.get_from_first_row(lambda row: row['activation_code'].decode('utf-8'),
                                    printer=printer))

def print_activation_code():

    args = Arg.parse_serial_target()
    printer = StatusPrinter(indent=0)
    printer("Getting Activation Code")

    with Indent(printer):
        print(get_activation_code(args.target, args.serial_num, printer=printer))

def get_acceptedness(target, serial_num, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT value
            FROM setting
            WHERE merchant_id IN
                    (SELECT merchant_id
                     FROM device_provision
                     WHERE serial_number = '{}')
                AND
                    name = 'ACCEPTED_BILLING_TERMS';
             """.format(serial_num))

    q.on_empty("this device is not associated with a merchant on {}".format(target.get_name()))

    try:
        value = q.get_from_first_row(lambda row: row['value'],
                printer=printer)
    except ValueError as ex:
        printer(str(ex))
        sys.exit(40)

    if value is None:
        return None
    else:
        return value.decode('utf-8')

def set_acceptedness(target, serial_num, value, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE setting SET value = {}
            WHERE merchant_id IN
                    (SELECT merchant_id
                     FROM device_provision
                     WHERE serial_number = '{}')
                AND
                    name = 'ACCEPTED_BILLING_TERMS';
             """.format(value, serial_num))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed != 1:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def set_activation_code(target, serial_num, value, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE device_provision SET activation_code = {}
            WHERE serial_number = '{}';
             """.format(value, serial_num))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed != 1:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_set_activation():

    args = Arg.parse_serial_target_code()
    printer = StatusPrinter(indent=0)

    printer("Checking Activation Code")
    with Indent(printer):
        old_code = get_activation_code(args.target, args.serial_num, printer=printer)

    if old_code == args.activation_code:
        printer("No change needed")
    else:
        printer("Setting Activation Code")
        with Indent(printer):
            set_activation_code(args.target, args.serial_num, args.activation_code, printer=printer)

def get_last_activation_code(target, serial_num, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT last_activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial_num))

    q.on_empty("This device is not known to {}".format(target.get_name()))

    return int(q.get_from_first_row(lambda row: row['last_activation_code'].decode('utf-8'),
                                    printer=printer))

def describe_increment_last_activation_code(target, serial_num, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE device_provision
            SET last_activation_code = last_activation_code + 1
            WHERE serial_number = '{}';
            """.format(serial_num))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed == 1:
        return SetResult(True, "The activation code is now fresh")
    else:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_refresh_activation():

    args = Arg.parse_serial_target()
    printer = StatusPrinter(indent=0)

    printer("Checking Last Activation Code")
    with Indent(printer):
        new_code = get_activation_code(args.target, args.serial_num, printer=printer)

    printer("Checking Current Activation Code")
    with Indent(printer):
        old_code = get_last_activation_code(args.target, args.serial_num, printer=printer)

    if old_code != new_code:
        printer("Code is fresh, no change needed")
    else:
        printer("Code is stale, incrementing last_activation_code")
        with Indent(printer):
            result = describe_increment_last_activation_code(args.target, args.serial_num, printer=printer)
        printer(result.description)

def unaccept():

    args = Arg.parse_serial_target()
    printer = StatusPrinter(indent=0)
    printer("Clearing Terms Acceptance")

    with Indent(printer):

        desired_value = '\'0\''
        # yes, that's the string containing 0
        # word on the street is that it's better than 0 or null

        printer("Checking Acceptedness")
        with Indent(printer):
            accepted = get_acceptedness(args.target, args.serial_num, printer=printer)

        if accepted == desired_value.strip('\''):
            printer("Already cleared, no change needed")
        else:
            printer("Revoking Acceptedness")
            with Indent(printer):
                set_acceptedness(args.target, args.serial_num, desired_value, printer=printer)
    printer("OK")

def accept():

    args = Arg.parse_serial_target()
    printer = StatusPrinter()
    printer("Accepting Terms")

    set_acceptedness(args.target, args.serial_num, "1")

    new_val = get_acceptedness(args.target, args.serial_num)
    if new_val == "1":
        print("OK", file=sys.stderr)
    else:
        raise ValueError("Failed to set acceptedness to {}.  Final value: {}".format("1", new_val))

# given a url and a server, get the auth token for that url on that server
def get_auth_token(target, url, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT HEX(at.uuid)
            FROM authtoken at
            JOIN authtoken_uri atu
                ON at.id = atu.authtoken_id
            WHERE
                    atu.uri = '{}'
                AND
                    at.deleted_time IS NULL LIMIT 1;
            """.format(url))

    auth_token = q.get_from_first_row(lambda row: row['HEX(at.uuid)'].decode('utf-8'), printer=printer)

    if not re.match(r'^[A-Z0-9]+$', auth_token):
        raise ValueError("Http header: 'AUTHORIZATION : BEARER {}' doesn't seem right.".format(auth_token))

    return auth_token

# get the mid of the merchant with this uuid
def get_mid(target, uuid, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
                SELECT id FROM merchant WHERE uuid='{}' LIMIT 1;
            """.format(uuid))

    mid_str = q.get_from_first_row(lambda row: row['id'], printer=printer)

    return int(mid_str)

# print the mid of the merchant with the specified uuid
def print_merchant_id():

    args = Arg.parse_merchant_target()
    print(get_mid(args.target, args.merchant_uuid))

# deprovision device from merchant
def deprovision():

    args = Arg.parse_serial_target()
    printer = StatusPrinter(indent=0)
    printer("Deprovisioning Device")
    with Indent(printer):

        auth_token = get_auth_token(args.target,
                '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/deprovision')

        mid = get_merchant(args.serial_num, args.target, printer=printer).uuid

        endpoint = 'https://{}/v3/partner/pp/merchants/{}/devices/{}/deprovision'.format(
                    args.target.hostname,
                    mid,
                    args.serial_num)

        headers = { 'Authorization' : 'Bearer ' + auth_token }

        print_request(printer, endpoint, headers, {})
        response = requests.put(endpoint, headers = headers)
        print_response(printer, response)

    # TODO: server/scripts/disassociate_device.py also DELETEs '/v3/resellers/{rId}/devices/{serial}'
    # maybe this function should do that also?

    if response.status_code == 200:
        printer('OK')
    else:
        printer('Error')
        sys.exit(10)

# provision device for merchant
def provision():

    args = Arg.parse_serial_target_merch()
    printer = StatusPrinter(indent=0)
    printer("Provisioning Device")
    with Indent(printer):

        printer("Checking merchant reseller")
        skipResellerCheck = False
        with Indent(printer):
            merchant_reseller = get_merchant_reseller(args.merchant, args.target, printer=printer).id

        printer("Ensuring device/merchant resellers match")
        with Indent(printer):
            try:
                result = describe_set_device_reseller(args.serial_num, args.target, merchant_reseller, printer=printer)
                if result.change_made:
                    printer(result.descrption)
            except ValueError as err:
                if "not associated" in str(err):
                    printer("Device not provisioned, so no conflicting reseller exists")

        endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                args.target.get_hypertext_protocol(),
                args.target.get_hostname() + ":" + args.target.get_http_port(),
                args.merchant,
                args.serial_num)

        printer("Getting provision endpoint auth token")
        with Indent(printer):
            auth_token = get_auth_token(args.target,
                    '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision',
                    printer=printer)

        printer("Provisioning device to merchant")
        with Indent(printer):
            headers = {'Authorization' : 'Bearer ' + auth_token }

            data = {'mId': get_mid(args.target, args.merchant, printer=printer),
                    'merchantUuid': args.merchant,
                    'serial': args.serial_num,
                    'chipUid': args.cpuid}

            print_request(printer, endpoint, headers, data)

            response = requests.put(endpoint, headers = headers, data=data)

            print_response(printer, response)

    if response.status_code == 200:
        printer('OK')
    else:
        printer('Error')
        sys.exit(20)

def create_merchant():

    base_message = textwrap.dedent(
    """
    <XMLRequest>
        <RequestAction>Create</RequestAction>
        <MerchantDetail>
            <MerchantNumber></MerchantNumber>
            <TimeZone>Pacific/Samoa</TimeZone>
            <ABAAccountNumber></ABAAccountNumber>
            <ACHBankID></ACHBankID>
            <DaylightSavings>N</DaylightSavings>
            <SeasonalInd>N</SeasonalInd>
            <ExternalMerchantInd>N</ExternalMerchantInd>
            <DynamicDBA>N</DynamicDBA>
            <TaxExemptInd>N</TaxExemptInd>
            <ValueLinkInd>N</ValueLinkInd>
        </MerchantDetail>
        <ShipAddress></ShipAddress>
    </XMLRequest>
    """)
    return base_message

def print_new_merchant():
    print(create_merchant())


# provision device for new merchant
def provision_new():
    args = Arg.parse_serial_target_merch_reseller()
    printer = StatusPrinter(indent=0)
    printer("Provisioning New Device")
    with Indent(printer):

        printer("Checking merchant reseller")
        skipResellerCheck = False
        with Indent(printer):
            merchant_reseller = get_merchant_reseller(args.merchant, args.target, printer=printer).id

        printer("Ensuring device/merchant resellers match")
        with Indent(printer):
            try:
                result = describe_set_device_reseller(args.serial_num, args.target, merchant_reseller, printer=printer)
                if result.change_made:
                    printer(result.descrption)
            except ValueError as err:
                if "not associated" in str(err):
                    printer("Device not provisioned, so no conflicting reseller exists")

        endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                args.target.get_hypertext_protocol(),
                args.target.get_hostname() + ":" + args.target.get_http_port(),
                args.merchant,
                args.serial_num)

        printer("Getting provision endpoint auth token")
        with Indent(printer):
            auth_token = get_auth_token(args.target,
                    '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision',
                    printer=printer)

        printer("Provisioning device to merchant")
        with Indent(printer):
            headers = {'Authorization' : 'Bearer ' + auth_token }

            data = {'mId': get_mid(args.target, args.merchant, printer=printer),
                    'merchantUuid': args.merchant,
                    'serial': args.serial_num,
                    'chipUid': args.cpuid}

            print_request(printer, endpoint, headers, data)

            response = requests.put(endpoint, headers = headers, data=data)

            print_response(printer, response)

    if response.status_code == 200:
        printer('OK')
    else:
        printer('Error')
        sys.exit(20)
