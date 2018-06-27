import sys
import os
import re
import json
import textwrap
import argparse
import xml.etree.ElementTree as ET
from collections import namedtuple
from argparse import ArgumentParser
from scoobe.cli import parse, Parsable as Arg
from scoobe.common import StatusPrinter, Indent
from scoobe.http import get, put, post
from scoobe.ssh import SshConfig, UserPass
from scoobe.mysql import Query
from scoobe.properties import LocalServer

def get_creds(printer=StatusPrinter()):

    user_exists = False
    user_var='LDAP_USER'
    if user_var in os.environ:
        user = os.environ[user_var]
        user_exists = True
    # else: warn later so we can warn for both

    passwd_exists=False
    passwd_var='LDAP_PASSWORD'
    if passwd_var in os.environ:
        passwd = os.environ[passwd_var]
        passwd_exists = True
    # else: warn later so we can warn for both

    try:
        return UserPass(user, passwd)
    except NameError:
        with Indent(printer):
            printer("Please set environment variables:")
            with Indent(printer):

                if not user_exists:
                    printer(user_var)
                    with Indent(printer):
                        printer("(try typing: 'export {}=<your_username>' and rerunning the command)".format(
                            user_var))

                if not passwd_exists:
                    printer(passwd_var)
                    with Indent(printer):
                        printer("(try typing: \'read -s {} && export {}\', ".format(passwd_var, passwd_var),
                                "typing your password, and rerunning the command)")
                if not (user_exists and passwd_exists):
                    sys.exit(100)

def internal_auth(target,
                  creds = {'username' : 'joe.blow',
                           'password' : 'letmein' },
                  printer=StatusPrinter()):

    endpoint = '{}://{}/cos/v1/dashboard/internal/login'.format(
                target.get_hypertext_protocol(),
                target.get_hostname() + ":" + str(target.get_http_port()))

    headers = { 'Content-Type' : 'application/json ',
                      'Accept' : 'application/json, text/javascript, */*; q=0.01',
                  'Connection' : 'keep-alive' }

    data = creds

    response = post(endpoint, headers, data, obfuscate_pass=True, printer=printer)

    if response.status_code == 200:
        return response.headers['set-cookie']
    elif response.status_code == 401:
        printer("{} has cloverDevAuth unset, looking for real credentials".format(target.get_name()))

        creds = get_creds(printer=printer)
        data = {'username' : creds.user,
                'password' : creds.passwd}

        response = post(endpoint, headers, data, obfuscate_pass=True, printer=printer)

        if response.status_code == 200:
            return response.headers['set-cookie']
    else:
        raise Exception("Unexpected response from login endpoint")


def print_cookie():
    args = parse(Arg.target)
    printer = StatusPrinter(indent=0)

    printer("Getting a login cookie from {}".format(args.target.get_name()))
    with Indent(printer):
        cookie = internal_auth(args.target, printer=printer)

    if cookie:
        print(cookie)


Merchant = namedtuple('Merchant', 'id uuid')
def get_merchant(serial, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id, uuid
            FROM merchant
            WHERE id = (SELECT merchant_id
                        FROM device_provision
                        WHERE serial_number = '{}');
            """.format(serial))

    q.on_empty("this device is not associated with a merchant on {}".format(target.get_name()))

    return q.get_from_first_row(
            lambda row: Merchant(row['id'], row['uuid'].decode('utf-8')),
            printer=printer)

def print_merchant():

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s merchant according to {}".format(args.serial, args.target.get_name()))
        with Indent(printer):
            merchant = get_merchant(args.serial, args.target, printer=printer)
        print(json.dumps(merchant._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

# returns the merchant currently associated with the specified device
Reseller = namedtuple('Reseller', 'id uuid name')
def get_device_reseller(serial, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id, uuid, name
            FROM reseller
            WHERE id = (SELECT reseller_id
                        FROM device_provision
                        WHERE serial_number = '{}');
            """.format(serial))

    q.on_empty("this device is not associated with a reseller according to {}".format(target.get_name()))

    return q.get_from_first_row(
            lambda row: Reseller(row['id'], row['uuid'].decode('utf-8'), row['name'].decode('utf-8')),
            printer=printer)

def print_device_reseller():

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(args.serial, args.target.get_name()))
        with Indent(printer):
            merchant = get_device_reseller(args.serial, args.target, printer=printer)
        print(json.dumps(merchant._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(90)


SetResult = namedtuple('SetResult', 'change_made description')
def describe_set_device_reseller(serial, target, target_reseller_id, printer=StatusPrinter()):

    printer("Checking the device's reseller")
    with Indent(printer):
        current_reseller = get_device_reseller(serial, target, printer)

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
                    """.format(target_reseller_id, serial))

            rows_changed = q.run_get_rows_changed(printer=printer)
            if rows_changed == 1:
                return SetResult(False, "NOTICE: the attached device's reseller has changed from {} to {}".format(
                                        current_reseller.id, target_reseller_id))
            else:
                raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_set_device_reseller():

    args = parse(Arg.serial, Arg.target, Arg.reseller)
    printer = StatusPrinter(indent=0)

    printer("Setting the device's reseller to {}".format(args.reseller))
    with Indent(printer):
        result = describe_set_device_reseller(args.serial, args.target, args.reseller, printer=printer)
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

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(args.merchant, args.target.get_name()))
        with Indent(printer):
            reseller = get_merchant_reseller(args.merchant, args.target, printer=printer)
        print(json.dumps(reseller._asdict()))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def get_activation_code(target, serial, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial))

    q.on_empty("This device is not known to {}".format(target.get_name()))

    return int(q.get_from_first_row(lambda row: row['activation_code'].decode('utf-8'),
                                    printer=printer))

def print_activation_code():

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)
    printer("Getting Activation Code")

    with Indent(printer):
        print(get_activation_code(args.target, args.serial, printer=printer))

def get_acceptedness(target, serial, printer=StatusPrinter()):

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
             """.format(serial))

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

def set_acceptedness(target, serial, value, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE setting SET value = {}
            WHERE merchant_id IN
                    (SELECT merchant_id
                     FROM device_provision
                     WHERE serial_number = '{}')
                AND
                    name = 'ACCEPTED_BILLING_TERMS';
             """.format(value, serial))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed != 1:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def set_activation_code(target, serial, value, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE device_provision SET activation_code = {}
            WHERE serial_number = '{}';
             """.format(value, serial))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed != 1:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_set_activation():

    args = parse(Arg.serial, Arg.target, Arg.code)
    printer = StatusPrinter(indent=0)

    printer("Checking Activation Code")
    with Indent(printer):
        old_code = get_activation_code(args.target, args.serial, printer=printer)

    if old_code == args.code:
        printer("No change needed")
    else:
        printer("Setting Activation Code")
        with Indent(printer):
            set_activation_code(args.target, args.serial, args.code, printer=printer)

def get_last_activation_code(target, serial, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT last_activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial))

    q.on_empty("This device is not known to {}".format(target.get_name()))

    return int(q.get_from_first_row(lambda row: row['last_activation_code'].decode('utf-8'),
                                    printer=printer))

def describe_increment_last_activation_code(target, serial, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE device_provision
            SET last_activation_code = last_activation_code + 1
            WHERE serial_number = '{}';
            """.format(serial))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed == 1:
        return SetResult(True, "The activation code is now fresh")
    else:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_refresh_activation():

    args = Arg.parse(Args.serial, Args.target)
    printer = StatusPrinter(indent=0)

    printer("Checking Last Activation Code")
    with Indent(printer):
        new_code = get_activation_code(args.target, args.serial, printer=printer)

    printer("Checking Current Activation Code")
    with Indent(printer):
        old_code = get_last_activation_code(args.target, args.serial, printer=printer)

    if old_code != new_code:
        printer("Code is fresh, no change needed")
    else:
        printer("Code is stale, incrementing last_activation_code")
        with Indent(printer):
            result = describe_increment_last_activation_code(args.target, args.serial, printer=printer)
        printer(result.description)

def unaccept():

    args = Arg.parse(Args.serial, Args.target)
    printer = StatusPrinter(indent=0)
    printer("Clearing Terms Acceptance")

    with Indent(printer):

        desired_value = '\'0\''
        # yes, that's the string containing 0
        # word on the street is that it's better than 0 or null

        printer("Checking Acceptedness")
        with Indent(printer):
            accepted = get_acceptedness(args.target, args.serial, printer=printer)

        if accepted == desired_value.strip('\''):
            printer("Already cleared, no change needed")
        else:
            printer("Revoking Acceptedness")
            with Indent(printer):
                set_acceptedness(args.target, args.serial, desired_value, printer=printer)
    printer("OK")

def accept():

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter()
    printer("Accepting Terms")

    set_acceptedness(args.target, args.serial, "1")

    new_val = get_acceptedness(args.target, args.serial)
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

    args = parse(Arg.merchant, Arg.target)
    print(get_mid(args.target, args.merchant))

# deprovision device from merchant
def deprovision():

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)
    printer("Deprovisioning Device")
    with Indent(printer):

        auth_token = get_auth_token(args.target,
                '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/deprovision')

        mid = get_merchant(args.serial, args.target, printer=printer).uuid

        endpoint = 'https://{}/v3/partner/pp/merchants/{}/devices/{}/deprovision'.format(
                    args.target.hostname,
                    mid,
                    args.serial)

        headers = { 'Authorization' : 'Bearer ' + auth_token }

        response = put(endpoint, headers, printer=printer)

    # TODO: server/scripts/disassociate_device.py also DELETEs '/v3/resellers/{rId}/devices/{serial}'
    # maybe this function should do that also?

    if response.status_code == 200:
        printer('OK')
    else:
        printer('Error')
        sys.exit(10)

# provision device for merchant
def provision():

    args = parse(Arg.serial, Arg.target, Arg.merchant)
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
                result = describe_set_device_reseller(args.serial, args.target, merchant_reseller, printer=printer)
                if result.change_made:
                    printer(result.descrption)
            except ValueError as err:
                if "not associated" in str(err):
                    printer("Device not provisioned, so no conflicting reseller exists")

        endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                args.target.get_hypertext_protocol(),
                args.target.get_hostname() + ":" + args.target.get_http_port(),
                args.merchant,
                args.serial)

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
                    'serial': args.serial,
                    'chipUid': args.cpuid}

            response = put(endpoint, headers, data, printer=printer)

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
    args = parse(Arg.serial, Arg.target, Arg.merchant, Arg.reseller)
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
                result = describe_set_device_reseller(args.serial, args.target, merchant_reseller, printer=printer)
                if result.change_made:
                    printer(result.descrption)
            except ValueError as err:
                if "not associated" in str(err):
                    printer("Device not provisioned, so no conflicting reseller exists")

        endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                args.target.get_hypertext_protocol(),
                args.target.get_hostname() + ":" + args.target.get_http_port(),
                args.merchant,
                args.serial)

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
                    'serial': args.serial,
                    'chipUid': args.cpuid}

            response = put(endpoint, headers, data, printer=printer)

    if response.status_code == 200:
        printer('OK')
    else:
        printer('Error')
        sys.exit(20)
