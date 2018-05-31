import sys
import re
import requests
import json
from collections import namedtuple
from argparse import ArgumentParser
from scoobe.common import StatusPrinter, Indent, print_request, print_response
from scoobe.ssh import SshConfig
from scoobe.mysql import Query

# grab the serial number and ssh config from the command line
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

# returns the merchant currently associated with the specified device
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

    q.on_empty("this device is not associated with a merchant on {}".format(ssh_config.ssh_host))

    return q.get_from_first_row(
            lambda row: Merchant(row['id'], row['uuid'].decode('utf-8')),
            printer=printer)

# prints a json dictionary { "id" : "the_mid", "uuid" : "the_uuid" }
def print_merchant():
    args = parse_serial_ssh()

    printer = StatusPrinter(indent=0)
    printer("Finding {}'s merchant according to {}".format(args.serial_num, args.ssh_config.ssh_host))

    try:
        with Indent(printer):
            merchant = get_merchant(args.serial_num, args.ssh_config, printer=printer)
        print(json.dumps(merchant._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def print_activation_code():
    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)
    printer("Getting Activation Code")
    with Indent(printer):
        print(get_activation_code(args.ssh_config, args.serial_num, printer=printer))

def get_activation_code(ssh_config, serial_num, printer=StatusPrinter()):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial_num))

    q.on_empty("This device is not known to {}".format(ssh_config.ssh_host))

    return int(q.get_from_first_row(lambda row: row['activation_code'].decode('utf-8'),
                                    printer=printer))

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

    q.on_empty("this device is not associated with a merchant on {}".format(ssh_config.ssh_host))

    try:
        value = q.get_from_first_row(lambda row: row['value'])
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
    q.execute()

def unaccept():
    args = parse_serial_ssh()
    printer = StatusPrinter(indent=0)
    printer("Clearing Terms Acceptance")

    set_acceptedness(args.ssh_config, args.serial_num, "NULL", printer)

    new_val = get_acceptedness(args.ssh_config, args.serial_num, printer)

    if new_val is None:
        printer("OK")
    else:
        raise ValueError("Failed to set acceptedness to {}.  Final value: {}".format("NULL", new_val))

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
def get_auth_token(ssh_config, url):

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

    auth_token = q.get_from_first_row(lambda row: row['HEX(at.uuid)'].decode('utf-8'))

    if not re.match(r'^[A-Z0-9]+$', auth_token):
        raise ValueError("Http header: 'AUTHORIZATION : BEARER {}' doesn't seem right.".format(auth_token))

    return auth_token

# get the mid of the merchant with this uuid
def get_mid(ssh_config, uuid):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
                SELECT id FROM merchant WHERE uuid='{}' LIMIT 1;
            """.format(uuid))

    mid_str = q.get_from_first_row(lambda row: row['id'])

    return int(mid_str)

# print the mid of the merchant with the specified uuid
def print_merchant_id():
    parser = ArgumentParser()
    parser.add_argument("serial_num", type=str, help="the device serial number")
    parser.add_argument("ssh_config_host", type=str, help="ssh host of the server (specified in ~/.ssh/config)")
    parser.add_argument("merchant_uuid", type=str,
            help="the merchant uuid that we want a merchant id for")
    args = parser.parse_args()

    printer = StatusPrinter(indent=0)
    printer("Finding {}'s id  according to {}".format(args.merchant_uuid, args.ssh_config_host))

    if not re.match(r'[A-Za-z0-9]{13}', args.merchant_uuid):
       raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant_uuid))

    ssh_config = SshConfig(args.ssh_config_host)
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

        endpoint = 'https://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                args.ssh_config.hostname,
                args.merchant,
                args.serial_num)

        auth_token = get_auth_token(args.ssh_config,
                '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision')

        headers = {'Authorization' : 'Bearer ' + auth_token }

        data = {'mId': get_mid(args.ssh_config, args.merchant),
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
