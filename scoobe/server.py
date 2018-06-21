import sys
import re
import requests
import json
from collections import namedtuple
from argparse import ArgumentParser
from scoobe.common import StatusPrinter, Indent, print_request, print_response
from scoobe.ssh import SshConfig
from scoobe.mysql import Query

# parse cli args, return one of these:
SerialSsh = namedtuple('SerialSsh', 'serial_num ssh_config')
def parse_serial_ssh():
    parser = ArgumentParser()
    parser.add_argument("serial_num", type=str, help="the device serial number")
    parser.add_argument("ssh_config_host", type=str, help="ssh host of the server (specified in ~/.ssh/config)")
    args = parser.parse_args()

    if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
       raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

    ssh_config = SshConfig(args.ssh_config_host)

    return SerialSsh(args.serial_num, ssh_config)

# parse cli args, return one of these:
SerialSshCode = namedtuple('SerialSsh', 'serial_num ssh_config activation_code')
def parse_serial_ssh_code():
    parser = ArgumentParser()
    parser.add_argument("serial_num", type=str, help="the device serial number")
    parser.add_argument("ssh_config_host", type=str, help="ssh host of the server (specified in ~/.ssh/config)")
    parser.add_argument("activation_code", type=str, help="the desired activation code")
    args = parser.parse_args()

    if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
       raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

    ssh_config = SshConfig(args.ssh_config_host)

    return SerialSshCode(args.serial_num, ssh_config, args.activation_code)

# parse cli args, return one of these:
SerialSshReseller = namedtuple('SerialSshReseller', 'serial_num ssh_config reseller_id')
def parse_serial_ssh_reseller():

    parser = ArgumentParser()
    parser.add_argument("serial_num", type=str, help="the device serial number")
    parser.add_argument("ssh_config_host", type=str, help="ssh host of the server (specified in ~/.ssh/config)")
    parser.add_argument("reseller_id", type=int, help="the reseller id (int)")
    args = parser.parse_args()

    if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
       raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

    ssh_config = SshConfig(args.ssh_config_host)

    if not args.reseller_id >= 0:
       raise ValueError("{} doesn't look like a reseller_id".format(args.reseller_id))

    return SerialSshReseller(args.serial_num, ssh_config, args.reseller_id)

# parse cli args, return one of these:
MerchantSsh = namedtuple('MerchantSsh', 'merchant_uuid ssh_config')
def parse_merchant_ssh():

    parser = ArgumentParser()
    parser.add_argument("merchant_uuid", type=str, help="the uuid of the merchant")
    parser.add_argument("ssh_config_host", type=str, help="ssh host of the server (specified in ~/.ssh/config)")
    args = parser.parse_args()

    if not re.match(r'[A-Za-z0-9]{13}', args.merchant_uuid):
       raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant_uuid))

    ssh_config = SshConfig(args.ssh_config_host)

    return MerchantSsh(args.merchant_uuid, ssh_config)

Merchant = namedtuple('Merchant', 'id uuid')
def get_merchant(serial_num, ssh_config, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT id, uuid
            FROM merchant
            WHERE id = (SELECT merchant_id
                        FROM device_provision
                        WHERE serial_number = '{}');
            """.format(serial_num))

    q.on_empty("this device is not associated with a merchant on {}".format(ssh_config.get_name()))

    return q.get_from_first_row(
            lambda row: Merchant(row['id'], row['uuid'].decode('utf-8')),
            printer=printer)

def print_merchant():

    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s merchant according to {}".format(args.serial_num, args.ssh_config.get_name()))
        with Indent(printer):
            merchant = get_merchant(args.serial_num, args.ssh_config, printer=printer)
        print(json.dumps(merchant._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

# returns the merchant currently associated with the specified device
Reseller = namedtuple('Reseller', 'id uuid name')
def get_device_reseller(serial_num, ssh_config, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT id, uuid, name
            FROM reseller
            WHERE id = (SELECT reseller_id
                        FROM device_provision
                        WHERE serial_number = '{}');
            """.format(serial_num))

    q.on_empty("this device is not associated with a reseller on {}".format(ssh_config.get_name()))

    return q.get_from_first_row(
            lambda row: Reseller(row['id'], row['uuid'].decode('utf-8'), row['name'].decode('utf-8')),
            printer=printer)

def print_device_reseller():

    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)

    printer("Finding {}'s reseller according to {}".format(args.serial_num, args.ssh_config.get_name()))
    with Indent(printer):
        merchant = get_device_reseller(args.serial_num, args.ssh_config, printer=printer)
    print(json.dumps(merchant._asdict()))

SetResult = namedtuple('SetResult', 'change_made description')
def describe_set_device_reseller(serial_num, ssh_config, target_reseller_id, printer=StatusPrinter()):

    printer("Checking the device's reseller")
    with Indent(printer):
        current_reseller = get_device_reseller(serial_num, ssh_config, printer)

    # don't modify if desired value is already set
    if int(current_reseller.id) == int(target_reseller_id):
        return SetResult(False, "The device's current reseller is the same as the target reseller ({}), making no change"
                                .format(target_reseller_id))

    # otherwise motfdy
    else:
        printer("Changing the device's reseller: {} -> {}".format(current_reseller.id, target_reseller_id))
        with Indent(printer):

            q = Query(ssh_config, 'metaRW', 'test789',
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

    args = parse_serial_ssh_reseller()
    printer = StatusPrinter(indent=0)

    printer("Setting the device's reseller to {}".format(args.reseller_id))
    with Indent(printer):
        result = describe_set_device_reseller(args.serial_num, args.ssh_config, args.reseller_id, printer=printer)
    printer(result.description)

def get_merchant_reseller(merchant_uuid, ssh_config, printer=StatusPrinter()):
    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT id, uuid, name
            FROM reseller
            WHERE id = (SELECT reseller_id
                        FROM merchant
                        WHERE uuid = '{}');
            """.format(merchant_uuid))

    q.on_empty("this device is not associated with a reseller on {}".format(ssh_config.get_name()))

    return q.get_from_first_row(
            lambda row: Reseller(row['id'], row['uuid'].decode('utf-8'), row['name'].decode('utf-8')),
            printer=printer)

def print_merchant_reseller():
    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(args.merchant_uuid, args.ssh_config.get_name()))
        with Indent(printer):
            reseller = get_merchant_reseller(args.merchant_uuid, args.ssh_config, printer=printer)
        print(json.dumps(reseller._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def get_activation_code(ssh_config, serial_num, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial_num))

    q.on_empty("This device is not known to {}".format(ssh_config.get_name()))

    return int(q.get_from_first_row(lambda row: row['activation_code'].decode('utf-8'),
                                    printer=printer))

def print_activation_code():
    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)
    printer("Getting Activation Code")
    with Indent(printer):
        print(get_activation_code(args.ssh_config, args.serial_num, printer=printer))

def get_acceptedness(ssh_config, serial_num, printer=StatusPrinter()):
    q = Query(ssh_config, 'metaRO', 'test321',
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

    q.on_empty("this device is not associated with a merchant on {}".format(ssh_config.get_name()))

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

def set_acceptedness(ssh_config, serial_num, value, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRW', 'test789',
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

def set_activation_code(ssh_config, serial_num, value, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRW', 'test789',
            """
            UPDATE device_provision SET activation_code = {}
            WHERE serial_number = '{}';
             """.format(value, serial_num))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed != 1:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_set_activation():

    args = parse_serial_ssh_code()
    printer = StatusPrinter(indent=0)

    printer("Checking Activation Code")
    with Indent(printer):
        old_code = get_activation_code(args.ssh_config, args.serial_num, printer=printer)

    if old_code == args.activation_code:
        printer("No change needed")
    else:
        printer("Setting Activation Code")
        with Indent(printer):
            set_activation_code(args.ssh_config, args.serial_num, args.activation_code, printer=printer)

def get_last_activation_code(ssh_config, serial_num, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT last_activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial_num))

    q.on_empty("This device is not known to {}".format(ssh_config.get_name()))

    return int(q.get_from_first_row(lambda row: row['last_activation_code'].decode('utf-8'),
                                    printer=printer))

def describe_increment_last_activation_code(ssh_config, serial_num, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRW', 'test789',
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
    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)

    printer("Checking Last Activation Code")
    with Indent(printer):
        new_code = get_activation_code(args.ssh_config, args.serial_num, printer=printer)

    printer("Checking Current Activation Code")
    with Indent(printer):
        old_code = get_last_activation_code(args.ssh_config, args.serial_num, printer=printer)

    if old_code != new_code:
        printer("Code is fresh, no change needed")
    else:
        printer("Code is stale, incrementing last_activation_code")
        with Indent(printer):
            result = describe_increment_last_activation_code(args.ssh_config, args.serial_num, printer=printer)
        printer(result.description)

def unaccept():
    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)
    printer("Clearing Terms Acceptance")
    with Indent(printer):

        desired_value = '\'0\''
        # yes, that's the string containing 0
        # word on the street is that it's better than 0 or null

        printer("Checking Acceptedness")
        with Indent(printer):
            accepted = get_acceptedness(args.ssh_config, args.serial_num, printer=printer)

        if accepted == desired_value.strip('\''):
            printer("Already cleared, no change needed")
        else:
            printer("Revoking Acceptedness")
            with Indent(printer):
                set_acceptedness(args.ssh_config, args.serial_num, desired_value, printer=printer)
    printer("OK")

def accept():
    args = parse_serial_ssh()
    printer = StatusPrinter()
    printer("Accepting Terms")

    set_acceptedness(args.ssh_config, args.serial_num, "1")

    new_val = get_acceptedness(args.ssh_config, args.serial_num)
    if new_val == "1":
        print("OK", file=sys.stderr)
    else:
        raise ValueError("Failed to set acceptedness to {}.  Final value: {}".format("1", new_val))

# given a url and a server, get the auth token for that url on that server
def get_auth_token(ssh_config, url, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRO', 'test321',
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
def get_mid(ssh_config, uuid, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
                SELECT id FROM merchant WHERE uuid='{}' LIMIT 1;
            """.format(uuid))

    mid_str = q.get_from_first_row(lambda row: row['id'], printer=printer)

    return int(mid_str)

# print the mid of the merchant with the specified uuid
def print_merchant_id():
    args = parse_merchant_ssh()
    print(get_mid(ssh_config, args.merchant_uuid))

# deprovision device from merchant
def deprovision():
    args = parse_serial_ssh()

    printer = StatusPrinter(indent=0)
    printer("Deprovisioning Device")
    with Indent(printer):

        auth_token = get_auth_token(args.ssh_config,
                '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/deprovision')

        mid = get_merchant(args.serial_num, args.ssh_config, printer=printer).uuid

        endpoint = 'https://{}/v3/partner/pp/merchants/{}/devices/{}/deprovision'.format(
                    args.ssh_config.hostname,
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

# grab the serial number, cpuid, ssh config, and merchant from the command line
ProvisionArgs = namedtuple('ProvisionArgs', 'serial_num cpuid ssh_config merchant')
def parse_serial_ssh_merch():
    parser = ArgumentParser()
    parser.add_argument("serial_num", type=str, help="the device serial number")
    parser.add_argument("cpuid", type=str, help="the device cpu id")
    parser.add_argument("ssh_config_host", type=str, help="ssh host of the server (specified in ~/.ssh/config)")
    parser.add_argument("merchant", type=str,
            help="UUID of merchant that will be using this device")
    args = parser.parse_args()

    if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
       raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

    if not re.match(r'[A-Za-z0-9]{13}', args.merchant):
       raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant))

    if not re.match(r'[A-Fa-f0-9]{32}', args.cpuid):
       raise ValueError("{} doesn't look like a device cpuid".format(args.cpuid))

    ssh_config = SshConfig(args.ssh_config_host)

    return ProvisionArgs(args.serial_num, args.cpuid, ssh_config, args.merchant)

# provision device for merchant
def provision():
    args = parse_serial_ssh_merch()

    printer = StatusPrinter(indent=0)
    printer("Provisioning Device")
    with Indent(printer):

        printer("Checking merchant reseller")
        with Indent(printer):
            merchant_reseller = get_merchant_reseller(args.merchant, args.ssh_config, printer=printer).id

        printer("Ensuring device/merchant resellers match")
        with Indent(printer):
            result = describe_set_device_reseller(args.serial_num, args.ssh_config, merchant_reseller, printer=printer)
            if result.change_made:
                printer(result.descrption)

        endpoint = 'https://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                args.ssh_config.hostname,
                args.merchant,
                args.serial_num)

        printer("Getting provision endpoint auth token")
        with Indent(printer):
            auth_token = get_auth_token(args.ssh_config,
                    '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision',
                    printer=printer)

        printer("Provisioning device to merchant")
        with Indent(printer):
            headers = {'Authorization' : 'Bearer ' + auth_token }

            data = {'mId': get_mid(args.ssh_config, args.merchant, printer=printer),
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
