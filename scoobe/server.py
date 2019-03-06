import sys
import os
import re
import json
import textwrap
import datetime
import xmltodict
import time
import pprint as pp
from collections import namedtuple, OrderedDict
import xml.etree.ElementTree as ET
from scoobe.cli import parse, print_or_warn, Parseable, Region
from scoobe.common import StatusPrinter, Indent
from scoobe.http import get, put, post
from scoobe.ssh import SshConfig, UserPass
from scoobe.mysql import Query, Feedback
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

    # first try with with a nonsense user
    printer("Attempting cloverDevAuth")
    with Indent(printer):
        response = post(endpoint, headers, data, obfuscate_pass=True, printer=printer)

    if response.status_code == 200:
        return response.headers['set-cookie']

    # if that fails, use a real one
    elif response.status_code == 401:
        printer("{} has cloverDevAuth unset or false, looking for real credentials".format(target.get_name()))

        creds = get_creds(printer=printer)
        data = {'username' : creds.user,
                'password' : creds.passwd}

        with Indent(printer):
            response = post(endpoint, headers, data, obfuscate_pass=True, printer=printer)

            if response.status_code == 200:
                return response.headers['set-cookie']
            else:
                raise Exception("Unexpected response from login endpoint")

def print_cookie():
    parsed_args = parse(Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Getting a login cookie from {}".format(parsed_args.target.get_name()))
    with Indent(printer):
        cookie = internal_auth(parsed_args.target, printer=printer)

    if cookie:
        print(cookie)



def is_uuid(string):
    if re.match(r'[A-Za-z0-9]{13}', str(string)):
        return True
    return False

class ServerObject:
    def __str__(self):
        return json.dumps(self.__dict__)

class Reseller(ServerObject):
    def __init__(self, row):
        self.db_id = row['db_id']
        self.id = row['id']

    def apply_response(self, content):
        for key in [ 'name',                'alternateName',        'owner',                     'defaultPaymentProcessor',
                    'defaultProcessorKey',  'supportsNakedCredit',  'supportsOutboundBoarding',  'enforceMerchantPlan',
                    'supportPhone',         'supportEmail',         'filterApps',                'forcePhone',
                    'stationsOnClassic',    'createdTime',          'parentReseller',            'href',
                    'isBulkPurchaser',      'isRkiIdentifier',      'isSelfBoarding',            'isIntercomEnabled',
                    'locale' ]:
            try:
                setattr(self, key, content[key])
            except KeyError:
                pass

class Merchant(ServerObject):
    def __init__(self, row):
        self.db_id = row['db_id']
        self.id = row['id']
        self.reseller_id = row['reseller_id']

class PlanGroup(ServerObject):
    def __init__(self, row):
        self.db_id = row['db_id']
        self.id = row['id']
        self.name = row['name']
        self.enforce_assignment = row['enforce_assignment']
        self.trial_days = row['trial_days']

class Plan(ServerObject):
    def __init__(self, row):
        self.db_id = row['db_id']
        self.id = row['id']
        self.merchantPlanGroup_db_id = row['merchant_plan_group_id']

    def apply_response(self, content):
        for key in [ 'description', 'merchantPlanGroup', 'planCode', 'billToMid', 'defaultPlan', 'name', 'appBundle' ]:
            try:
                setattr(self, key, content[key])
            except KeyError:
                pass

class PartnerControl(ServerObject):
    def __init__(self, row):
        self.db_id = row['db_id']
        self.id = row['id']

    def apply_response(self, content):
        for key in [ 'enabled', 'modifyMatch', 'criteria', 'name' ]:
            try:
                setattr(self, key, content[key])
            except KeyError:
                pass

# given a merchant id or a merchant uuid, get both
def get_merchant(merchant, target, printer=StatusPrinter()):

    printer("Finding merchant {}'s identifiers according to {}".format(merchant, target.get_name()))
    with Indent(printer):
        if is_uuid(merchant):
            q = Query(target, 'metaRO', 'test321',
                    """
                    SELECT id as db_id, uuid as id, reseller_id
                    FROM merchant
                    WHERE uuid = '{}';
                    """.format(merchant))
        else:
            q = Query(target, 'metaRO', 'test321',
                    """
                    SELECT id as db_id, uuid as id, reseller_id
                    FROM merchant
                    WHERE id = {};
                    """.format(merchant))

        merchant = q.execute(Feedback.OneRow, lambda row : Merchant(row), printer=printer)

    if not merchant:
        printer("this merchant does not exist on {}".format(target.get_name()))

    return merchant

def print_merchant():

    parsed_args = parse(Parseable.merchant, Parseable.target)
    printer = StatusPrinter(indent=0)

    try:
        merchant = get_merchant(parsed_args.merchant, parsed_args.target, printer=printer)
        print(merchant)

    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

# given a serial number and a server, get the merchant associated with that serial number on that server
def get_device_merchant_id(serial, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT merchant_id
            FROM device_provision
            WHERE serial_number = '{}';
            """.format(serial))

    merchant_id = q.execute(Feedback.OneRow, lambda row : row['merchant_id'], printer=printer)

    if not merchant_id:
        raise ValueError("this device is not associated with a merchant on {}".format(target.get_name()))

    return merchant_id


def print_device_merchant():

    parsed_args = parse(Parseable.serial, Parseable.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s merchant according to {}".format(parsed_args.serial, parsed_args.target.get_name()))
        with Indent(printer):
            merchant_id = get_device_merchant_id(parsed_args.serial, parsed_args.target, printer=printer)

        printer("Finding merchant {}'s identifiers according to {}".format(merchant_id, parsed_args.target.get_name()))
        with Indent(printer):
            merchant = get_merchant(merchant_id, parsed_args.target, printer=printer)
        print(merchant)

    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def get_resellers(target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id as db_id, uuid as id, name, parent_id FROM reseller order by id;
            """)

    def as_dict(x):
        return {x['db_id'] : { 'id' : x['id'], 'name' : x['name'], 'parent_id' : x['parent_id']}}


    row_dicts = q.execute(Feedback.ManyRows, as_dict, print_transform = True, printer=printer)

    reseller_dict = {}
    for row_dict in row_dicts:
        reseller_dict.update(row_dict)
    return reseller_dict

def print_resellers():

    parsed_args = parse(Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Getting resellers according to {}".format(parsed_args.target.get_name()))
    with Indent(printer):
        resellers_dict = get_resellers(parsed_args.target, printer=printer)

    output = json.dumps(resellers_dict)

    printer('')
    print_or_warn(output, max_length=500)

def get_reseller(reseller, target, identifiers_only=False, and_channels=False, printer=StatusPrinter()):
    printer("Finding reseller {}'s identifiers according to {}".format(reseller, target.get_name()))
    with Indent(printer):
        if is_uuid(reseller):
            ident='uuid'
        else:
            ident='id'

        q = Query(target, 'metaRO', 'test321',
                """
                SELECT id as db_id, uuid as id
                FROM reseller
                WHERE {} = '{}';
                """.format(ident, reseller))

        reseller = q.execute(Feedback.OneRow, lambda row : Reseller(row), printer=printer)

    if identifiers_only:
        return reseller

    printer("Getting reseller {} from {}".format(reseller, target.get_name()))
    with Indent(printer):

        path='v3/resellers/{}'.format(reseller.id)

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json ',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        response = get(endpoint, headers, printer=printer)
        if response.status_code < 200 or response.status_code > 299:
            raise Exception("GET on {} returned code {}".format(endpoint, response.status_code))

        reseller.apply_response(json.loads(response.content.decode('utf-8')))

    if and_channels:

        def mark(prop, val):

            db2tag = { 'chain_agent' : { 'Agent'      : val },
                       'chain_bank'  : { 'Bank'       : val },
                       'marker'      : { 'BankMarker' : val },
                       'sysprin'     : { 'Sys-Prin'   : val },
                       'code'        : { 'Reseller'   : val } }

            if prop in db2tag:
                reseller.channel = db2tag[prop]

        printer("Finding reseller {}'s channels according to {}".format(reseller.id, target.get_name()))
        with Indent(printer):
            q = Query(target, 'metaRO', 'test321',
                    """
                    SELECT chain_agent, chain_bank, marker, sysprin
                    FROM reseller_channels
                    WHERE reseller_id = '{}';
                    """.format(reseller.db_id))
            channels = q.execute(Feedback.ManyRows)

            if not channels:
                raise ValueError("Can't board a merchant to a reseller if the reseller has no channels")

            # just need one
            marked = False
            for channel in channels[::-1]:
                if not marked:
                    for k, v in channel.items():
                        if v and not marked:
                            mark(k, v)
                            marked = True

            if not marked:
                raise ValueError("This reseller has no channels, how can a merchant be boarded?")

    return reseller

def print_get_reseller():

    parsed_args = parse(Parseable.reseller, Parseable.target)
    printer = StatusPrinter(indent=0)

    reseller = get_reseller(parsed_args.reseller, parsed_args.target, and_channels=True, printer=printer)

    print_or_warn(str(reseller), max_length=500)

def set_reseller(reseller_dict, target, printer=StatusPrinter()):

    printer("[Updating reseller from supplied json]")
    with Indent(printer):

        path='v3/resellers'

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        data = reseller_dict

        response = post(endpoint, headers, data, printer=printer)

        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

        return json.loads(response.content.decode('utf-8'))

def print_set_reseller():

    parsed_args = parse(Parseable.reseller_dict, Parseable.target)
    printer = StatusPrinter(indent=0)

    printer('foo')
    if 'id' in parsed_args.resellerdict:
        reseller = get_reseller(parsed_args.resellerdict['id'], parsed_args.target, printer)
    elif 'db_id' in parsed_args.resellerdict:
        reseller = get_reseller(parsed_args.resellerdict['db_id'], parsed_args.target, printer)
        parsed_args.resellerdict['id'] = reseller.id
    else:
        printer(textwrap.dedent(
            """It is not clear which reseller you want to update, maybe try new_reseller?
               Otherwise, specify either 'db_id' or 'id' (uuid) in the json, like so:
                 {
                   "id" : "SOMEPLANUUID"
                   "name" : "Foo Plan"
                   "description" : "I'm a reseller",
                 }
            """).strip())
        raise ValueError("Missing Required Data")


    result = set_reseller(parsed_args.resellerdict, parsed_args.target, printer=printer)

    printer("I've never seen this work.\n"
            "If you're reading this, it worked for you.\n"
            "I've been piping the output of get_reseller through jq to make a change and then pipping that output into this snac.\n"
            "Consider letting me know what you did so I can update the help accordingly.\n")

    print(result)


def get_device_reseller(serial, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id as db_id, uuid as id, name, parent_id
            FROM reseller
            WHERE id = (SELECT reseller_id
                        FROM device_provision
                        WHERE serial_number = '{}');
            """.format(serial))

    reseller = q.execute(Feedback.OneRow, lambda row : Reseller(row), printer=printer)

    if not reseller:
        printer("This device is not associated with a reseller according to {}".format(target.get_name()))

    return reseller

def print_device_reseller():

    parsed_args = parse(Parseable.serial, Parseable.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(parsed_args.serial, parsed_args.target.get_name()))
        with Indent(printer):
            reseller = get_device_reseller(parsed_args.serial, parsed_args.target, printer=printer)
        if reseller:
            print(json.dumps(reseller.__dict__))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(90)


# return true if desired state is achieved
# whether or not this function made a change
def set_device_reseller(serial, target, target_reseller, printer=StatusPrinter()):

    printer("Checking the device's reseller")
    with Indent(printer):
        current_reseller = get_device_reseller(serial, target, printer)

    if not current_reseller:
        printer("No device reseller found, setting it.")
        current_reseller = Reseller({'db_id' : 999999, 'id' : 'NONE', 'name' : 'NONE', 'parent_id' : 999999})

    # don't modify if desired value is already set
    if int(current_reseller.db_id) == int(target_reseller.db_id):
        printer("The device's current reseller is the same as the target reseller ({}). Making no change."
                                .format(target_reseller.db_id))
        return True

    # otherwise modify
    else:
        printer("Changing the device's reseller: {} -> {}".format(current_reseller.db_id, target_reseller.db_id))
        with Indent(printer):

            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE device_provision
                    SET reseller_id = {}
                    WHERE serial_number = '{}';
                    """.format(target_reseller.db_id, serial))

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)

            if rows_changed == 1:
                printer("NOTICE: the attached device's reseller has changed from {} to {}".format(
                                        current_reseller.db_id, target_reseller.db_id))
                return True
            else:
                raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def print_set_device_reseller():

    parsed_args = parse(Parseable.serial, Parseable.target, Parseable.reseller)
    printer = StatusPrinter(indent=0)

    printer("Setting device: {}'s reseller to {}".format(parsed_args.serial, parsed_args.reseller))
    with Indent(printer):
        reseller = get_reseller(parsed_args.reseller, parsed_args.target, printer=printer)
        if reseller:
            set_device_reseller(parsed_args.serial, parsed_args.target, reseller, printer=printer)
    printer("OK")

def print_merchant_reseller():

    parsed_args = parse(Parseable.merchant, Parseable.target)
    printer = StatusPrinter(indent=0)

    try:
        merchant = get_merchant(parsed_args.merchant, parsed_args.target, printer=printer)

        printer("Finding {}'s reseller according to {}".format(merchant.id, parsed_args.target.get_name()))
        with Indent(printer):
            reseller = get_reseller(merchant.reseller_id, parsed_args.target, printer=printer)
        if reseller:
            print(json.dumps(reseller.__dict__))
    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def get_activation_code(target, serial, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial))


    code = q.execute(Feedback.OneRow, lambda row: row['activation_code'], printer=printer)

    if not code:
        printer("This device is not known to {}".format(target.get_name()))

    if code == None:
        return None
    else:
        return int(code)

def print_activation_code():

    parsed_args = parse(Parseable.serial, Parseable.target)
    printer = StatusPrinter(indent=0)
    printer("Getting Activation Code")

    with Indent(printer):
        print(get_activation_code(parsed_args.target, parsed_args.serial, printer=printer))

def get_acceptedness(target, merchant_id, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT value
            FROM setting
            WHERE merchant_id = {} AND name = 'ACCEPTED_BILLING_TERMS';
             """.format(merchant_id))

    acceptedness_row = q.execute(Feedback.OneRow, lambda row: row['value'], printer=printer)

    if not acceptedness_row:
        printer("This device is not associated with a merchant on {}".format(target.get_name()))

    return acceptedness_row

def print_acceptedness():

    parsed_args = parse(Parseable.merchant, Parseable.target)
    printer = StatusPrinter(indent=0)

    merchant = get_merchant(parsed_args.merchant, parsed_args.target)

    printer("Checking Acceptedness Code")
    with Indent(printer):
        acceptedness = get_acceptedness(parsed_args.target, merchant.db_id, printer=printer)

    print(acceptedness)

def set_acceptedness(target, merchant_id, value, printer=StatusPrinter()):

    printer("Checking Current Value")
    with Indent(printer):
        current_value = get_acceptedness(target, merchant_id, printer=printer)

    # if no setting exists to frob
    if not(current_value):

        # warn, loudness depends on desired setting
        printer("Acceptedness is undefined for this merchant.  Have they gone through OOBE once already?")
        if value == '1':
            raise ValueError("Acceptedness setting does not exist, cannot enable it")
        else:
            # missing setting is equivaluent to disabled acceptedness, fail quietly
            pass

        return

    # if this action would produce an actual change, go ahead
    if str(current_value) != str(value):

        printer("Updating Value")
        with Indent(printer):
            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE setting SET value = '{}'
                    WHERE merchant_id = {} AND name = 'ACCEPTED_BILLING_TERMS';
                     """.format(value, merchant_id))

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)
            if rows_changed != 1:
                raise ValueError("Expected 1 change to table: setting, instead made {}".format(rows_changed))

    # Otherwise warn and quietly continue
    else:
        printer("No Change Needed")

def set_activation_code(target, serial, value, printer=StatusPrinter()):

    printer("Checking Current Value")
    with Indent(printer):
        old_value = get_activation_code(target, serial, printer=printer)

    if old_value != value:

        printer("Setting New Value")
        with Indent(printer):
            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE device_provision SET activation_code = {}
                    WHERE serial_number = '{}';
                     """.format(value, serial))

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)

            if rows_changed != 1:
                raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

        printer("Updating Historical Value")
        with Indent(printer):
            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE device_provision SET last_activation_code = {}
                    WHERE serial_number = '{}';
                     """.format(old_value, serial))

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)

            if rows_changed != 1:
                raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

    else:

        printer("No Change Needed")


def print_set_activation():

    parsed_args = parse(Parseable.serial, Parseable.target, Parseable.code)
    printer = StatusPrinter(indent=0)

    printer("Setting Activation Code to {}".format(parsed_args.code))
    with Indent(printer):
        set_activation_code(parsed_args.target, parsed_args.serial, parsed_args.code, printer=printer)

def get_last_activation_code(target, serial, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT last_activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial))

    last_activation_code = q.execute(Feedback.OneRow, lambda row : int(row['last_activation_code']))

    if not last_activation_code:
        raise ValueError("This device is not known to {}".format(target.get_name()))

    return last_activation_code

def describe_increment_last_activation_code(target, serial, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE device_provision
            SET last_activation_code = last_activation_code + 1
            WHERE serial_number = '{}';
            """.format(serial))

    rows_changed = q.execute(Feedback.ChangeCount, printer=printer)
    if rows_changed == 1:
        return SetResult(True, "The activation code is now fresh")
    else:
        raise ValueError("Expected 1 change to device_provision, instead {} were made".format(rows_changed))

def print_refresh_activation():

    parsed_args = parse(Parseable.serial, Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Refreshing Activation Code")
    with Indent(printer):

        printer("Checking Last Activation Code")
        with Indent(printer):
            new_code = get_activation_code(parsed_args.target, parsed_args.serial, printer=printer)

        printer("Checking Current Activation Code")
        with Indent(printer):
            old_code = get_last_activation_code(parsed_args.target, parsed_args.serial, printer=printer)

        if old_code != new_code:
            printer("Code is fresh, no change needed")

        else:
            printer("Code is stale, incrementing last_activation_code")
            with Indent(printer):
                result = describe_increment_last_activation_code(parsed_args.target, parsed_args.serial, printer=printer)
            printer(result.description)

def unaccept():

    parsed_args = parse(Parseable.merchant, Parseable.target)
    printer = StatusPrinter(indent=0)
    printer("Clearing Terms Acceptance")

    with Indent(printer):

        merchant = get_merchant(parsed_args.merchant, parsed_args.target, printer=printer)

        printer("Revoking Acceptedness")
        with Indent(printer):
            set_acceptedness(parsed_args.target, merchant.db_id, "0", printer=printer)

    printer("OK")

def accept():

    parsed_args = parse(Parseable.merchant, Parseable.target)
    printer = StatusPrinter()


    printer("Accepting Terms")
    with Indent(printer):

        merchant = get_merchant(parsed_args.merchant, parsed_args.target, printer=printer)

        set_acceptedness(parsed_args.target, merchant.db_id, "1")

    printer("OK")


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

    auth_token = q.execute(Feedback.OneRow, lambda row: row['HEX(at.uuid)'], printer=printer)

    if not re.match(r'^[A-Z0-9]+$', auth_token):
        raise ValueError("Http header: 'AUTHORIZATION : BEARER {}' doesn't seem right.".format(auth_token))

    return auth_token

# deprovision device from merchant
def deprovision():

    parsed_args = parse(Parseable.serial, Parseable.target)
    printer = StatusPrinter(indent=0)
    printer("Deprovisioning Device")
    with Indent(printer):

        try:

            printer("Finding device {}'s merchant according to {}".format(parsed_args.serial, parsed_args.target.get_name()))
            with Indent(printer):
                merchant_id = get_device_merchant_id(parsed_args.serial, parsed_args.target, printer=printer)

            printer("Getting the deprovision auth token according to {}".format(parsed_args.target.get_name()))
            with Indent(printer):
                auth_token = get_auth_token(parsed_args.target,
                        '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/deprovision')

            printer("Requesting that {} deprovision the device".format(parsed_args.target.get_name()))
            with Indent(printer):

                merchant = get_merchant(merchant_id, parsed_args.target, printer=printer)

                endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/deprovision'.format(
                            parsed_args.target.get_hypertext_protocol(),
                            parsed_args.target.get_hostname() + ":" + str(parsed_args.target.get_http_port()),
                            merchant.id,
                            parsed_args.serial)

                headers = { 'Authorization' : 'Bearer ' + auth_token }

                response = put(endpoint, headers, printer=printer, data={})

                # TODO: server/scripts/disassociate_device.py also DELETEs '/v3/resellers/{rId}/devices/{serial}'
                # maybe this function should do that also?

                if response.status_code != 200:
                    printer('Error')
                    sys.exit(10)


        except ValueError as ex:
            printer(str(ex))
            sys.exit(30)

    printer('OK')

# provision device for merchant
def provision():

    parsed_args = parse(Parseable.serial, Parseable.cpuid, Parseable.target, Parseable.merchant)
    printer = StatusPrinter(indent=0)
    printer("Provisioning Device")
    with Indent(printer):

        printer("Checking Merchant Reseller")
        with Indent(printer):
            merchant = get_merchant(parsed_args.merchant, parsed_args.target, printer=printer)
            merchant_reseller = get_reseller(merchant.reseller_id, parsed_args.target, printer=printer)

        printer("Ensuring device/merchant resellers match")
        with Indent(printer):

            try:
                success = set_device_reseller(parsed_args.serial, parsed_args.target, merchant_reseller, printer=printer)
            except ValueError as err:
                if "not associated" in str(err):
                    printer("Device not provisioned, so no conflicting reseller exists")
                    success = True

            # only proceed to provision if target merchant's reseller doesn't conflict
            if not success:
                sys.exit(313)

        printer("Getting provision endpoint auth token")
        with Indent(printer):
            auth_token = get_auth_token(parsed_args.target,
                    '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision',
                    printer=printer)

        printer("Provisioning device to merchant")
        with Indent(printer):

            endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                    parsed_args.target.get_hypertext_protocol(),
                    parsed_args.target.get_hostname() + ":" + str(parsed_args.target.get_http_port()),
                    merchant.id,
                    parsed_args.serial)

            headers = {'Authorization' : 'Bearer ' + auth_token }

            data = { 'merchantUuid': merchant.id,
                     'serial': parsed_args.serial,
                     'chipUid': parsed_args.cpuid }

            response = put(endpoint, headers, data, printer=printer)

    if response.status_code == 200:
        printer('OK')
    else:
        printer('Error')
        sys.exit(20)

us_path="/cos/v1/partner/fdc/create_merchant"
us_xml = """
<XMLRequest xmlns="http://soap.1dc.com/schemas/class/Crimson">
  <RequestAction>Create</RequestAction>
  <MerchantDetail>
    <CloverID></CloverID>
    <MerchantNumber>{mid}</MerchantNumber>
    <BEMerchantNumber>{bemid}</BEMerchantNumber>
    <Platform>N</Platform>
    <DBAName>{merchant_str}</DBAName>
    <LegalName>{merchant_str}</LegalName>
    <Address1>100 Penny Lane</Address1>
    <Address2 />
    <City>Nowhere Land</City>
    <State>TX</State>
    <Zip>11111</Zip>
    <Country>US</Country>
    <PhoneNumber>1111111111</PhoneNumber>
    <Email>{merchant_str}@dev.null.com</Email>
    <Contact>Nowhere Man</Contact>
    <MCCCode>5999</MCCCode>
    <IndustryCode>5999</IndustryCode>
    <Currency>USD</Currency>
    <TAEncryptionType>0001</TAEncryptionType>
    <GroupID>10001</GroupID>
    <TimeZone>CST</TimeZone>
    <SupportPhone>8003463315</SupportPhone>
    <ABAAccountNumber>000000053000196</ABAAccountNumber>
    <DDAAccountNumber>123444449000</DDAAccountNumber>
    <Business>177123456994</Business>
       <Bank>846980100883</Bank>
    <Corp />
    <Chain>177208700993</Chain>
    <ACHBankID>ACH123</ACHBankID>
    <AccountStatus>A1</AccountStatus>
    <BillToName>B2N</BillToName>
    <Store>100</Store>
    <DaylightSavings>Y</DaylightSavings>
    <SeasonalInd>Y</SeasonalInd>
    <TransArmorKey>11</TransArmorKey>
    <CreditLimit>1001.11</CreditLimit>
    <AuthLimit>1002.23</AuthLimit>
    <SaleLimit>1003.33</SaleLimit>
    <ExternalMerchantInd>Y</ExternalMerchantInd>
    <DynamicDBA>Y</DynamicDBA>
    <MerchFNSNum>FNS123</MerchFNSNum>
    <RelationshipManager>RM</RelationshipManager>
    <TaxExemptInd>Y</TaxExemptInd>
    <Salesman>Joe</Salesman>
    <ValueLinkInd>Y</ValueLinkInd>
    <ValueLinkMID>VL1</ValueLinkMID>
    <AltValueLinkMID>AV2</AltValueLinkMID>
    <ReceiptDBA>R123</ReceiptDBA>
    <ParentMerchantID>100</ParentMerchantID>
    <MultiMerchantType>C</MultiMerchantType>
    <MerchantData>md</MerchantData>
  </MerchantDetail>
  <ProgramExpressList>
    <ProgramExpress>
      <ProgramCode>1234</ProgramCode>
      <ProgramCodeDescription>pcd1</ProgramCodeDescription>
      <Key>123</Key>
      <KeyDescription>kd123</KeyDescription>
      <Value>v1</Value>
      <ValueDescription>vd</ValueDescription>
    </ProgramExpress>
  </ProgramExpressList>
  <CardTypes>
    <CardType CardName="MASTERCARD">
      <SENUMBER>177208700993</SENUMBER>
    </CardType>
    <CardType CardName="VISA">
      <SENUMBER>177208700993</SENUMBER>
    </CardType>
    <CardType CardName="EDS">
      <SENUMBER>000000084024335</SENUMBER>
    </CardType>
    <CardType CardName="PURCHASE CARD">
      <SENUMBER>000000989898989</SENUMBER>
    </CardType>
  </CardTypes>
  <DeviceList>
    <Device productType="1086">
      <DeviceType>Software</DeviceType>
      <ProductName>Clover Software RC</ProductName>
      <TerminalID>1282081</TerminalID>
      <ProcessingNetwork>Nashville</ProcessingNetwork>
      <DatawireID />
      <AutoCloseHour>5</AutoCloseHour>
      <CloseMethod>A</CloseMethod>
      <SerialNumber>123123123</SerialNumber>
      <DebitKeyCode>550</DebitKeyCode>
      <CloverVersion>Basic</CloverVersion>
    </Device>
        <Device productType="vsgl">
      <DeviceType>Software</DeviceType>
      <ProductName>Clover Software RC</ProductName>
      <TerminalID>1111</TerminalID>
      <ProcessingNetwork>Nashville</ProcessingNetwork>
      <DatawireID />
      <CloseMethod>A</CloseMethod>
      <SerialNumber>123123123</SerialNumber>
      <DebitKeyCode>550</DebitKeyCode>
      <CloverVersion>Basic</CloverVersion>
    </Device>
    <Device productType="1297">
      <DeviceType>Tablet</DeviceType>
      <ProductName>Clover Station 2018</ProductName>
      <EquipmentNumber>777</EquipmentNumber>
      <Status>Active</Status>
      <TerminalID/>
      <ProcessingNetwork>Nashville</ProcessingNetwork>
      <DatawireID />
      <CloseMethod>A</CloseMethod>
      <CloverVersion>Basic</CloverVersion>
    </Device>
    <Device productType="AOAN"><DeviceType>Tablet</DeviceType><ProductName>Clover Station</ProductName>
               <TerminalID/><ProcessingNetwork>Nashville</ProcessingNetwork><DatawireID/><AutoCloseHour/>
               <CloseMethod/><SerialNumber/><CloverVersion/><Status>Active</Status>
               <EquipmentNumber>
               10455215720011</EquipmentNumber><SerialNumber>C010UQ63567777</SerialNumber><BusinessType>Z</BusinessType><TransArmorInd/><ForceCloseTime>24
               </ForceCloseTime></Device>
  </DeviceList>
  <ShipAddress>
    <ShipName>Ben IVR TEST 7</ShipName>
    <ShipAttention>PINA DAVE</ShipAttention>
    <ShipAddress1>Ben WHITMAN RD</ShipAddress1>
    <ShipAddress2 />
    <ShipCity>MELVILLE</ShipCity>
    <ShipState>NY</ShipState>
    <ShipZip>11747</ShipZip>
  </ShipAddress>
</XMLRequest>
"""

eu_path="/cos/v1/partner/ipg/create_merchant"
eu_xml = """
<CloverBoardingRequest xmlns="com.clover.boarding">
  <RequestAction>Create</RequestAction>
  <MerchantDetail>
    <merchantNumber>{mid}</merchantNumber>
    <mid>{mid}</mid>
    <dbaName>UK-{merchant_str}</dbaName>
    <legalName>{merchant_str}</legalName>
    <address>
      <address1>UK drh</address1>
      <address2>45</address2>
      <city>London</city>
      <state>n/a</state>
      <zip>12345</zip>
      <country>GB</country>
    </address>
    <contactInformation>
      <contactName>Ben</contactName>
      <phoneNumber>1234567890</phoneNumber>
      <email>{merchant_str}@notavalidaddress.com</email>
    </contactInformation>
    <currency>EUR</currency>
    <timeZone>Pacific/Samoa</timeZone>
    <supportPhone>1234567890</supportPhone>
  </MerchantDetail>
  <CardTypes>
    <CardType cardName="VISA"/>
  </CardTypes>
  <ShipAddress>
    <shipAddress>
      <shipName>Test Register Lite 1</shipName>
      <address1>dtfvgbhjkn</address1>
      <address2>tyfgbhjkn</address2>
      <city>London</city>
      <state>n/a</state>
      <zip>12345</zip>
    </shipAddress>
  </ShipAddress>
</CloverBoardingRequest>
"""

def create_merchant(target, region, reseller, printer=StatusPrinter()):

    unique_str = str(datetime.datetime.utcnow().strftime('%s'))
    merchant_str = "merchant_" + unique_str + "BOARD_TO_SHARD_0"
    mid = int(unique_str)
    bemid = 8000000000 - mid

    if str(region) == 'US':
        toplevel='XMLRequest'
        path=us_path
        template=us_xml
    elif str(region) == 'EU':
        toplevel='CloverBoardingRequest'
        path=eu_path
        template=eu_xml
    else:
        raise ValueError("Unknown country code: {}".format(region))

    xml_d = xmltodict.parse(template.format(**locals()))

    # use reseller's first channel if defined, otherwise use reseller uuid
    tag, value = list(reseller.channel.items())[0]

    xml_d[toplevel]['MerchantDetail'][tag] = value

    xml = xmltodict.unparse(xml_d)

    printer(xml)

    endpoint = '{}://{}:{}{}'.format(
                target.get_hypertext_protocol(),
                target.get_hostname(),
                target.get_http_port(),
                path)

    headers = { 'Content-Type' : 'text/plain',
                      'Accept' : '*/*',
                      'Cookie' : internal_auth(target, printer=printer)}

    data = xml

    response = post(endpoint, headers, data, printer=printer)

    content = response.content.decode('utf-8')
    if 'prior placement' in content:
        raise Exception("The remote server tried to board this merchant to a nonexistent shard, maybe try again a few times.")


    response_dict = xmltodict.parse(content)
    return response_dict['XMLResponse']['Merchant']['UUID']

# return true if desired state is achieved
# whether or not this function made a change
def set_merchant_reseller(merchant, target, target_reseller, printer=StatusPrinter()):

    printer("Checking the merchant's current reseller")
    with Indent(printer):
        current_reseller = get_reseller(merchant.reseller_id, target, printer=printer)

    # don't modify if desired value is already set
    if int(current_reseller.db_id) == int(target_reseller.db_id):
        printer("The merchant's current reseller is the same as the target reseller ({}). Making no change."
                                .format(target_reseller.db_id))
        return True

    # otherwise modify
    else:
        printer("Changing the merchnat's reseller: {} -> {}".format(current_reseller.db_id, target_reseller.db_id))
        with Indent(printer):

            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE merchant
                    SET reseller_id = {}
                    WHERE id = '{}';
                    """.format(target_reseller.db_id, merchant.db_id))

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)

            if rows_changed == 1:
                printer("NOTICE: the merchant's reseller has changed from {} to {}".format(
                    current_reseller.db_id, target_reseller.db_id))
                return True
            else:
                raise ValueError("Expected 1 change to merchant, instead got {}".format(rows_changed))

def print_set_merchant_reseller():

    parsed_args = parse(Parseable.merchant, Parseable.reseller, Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Setting the merchant's reseller to {}".format(parsed_args.reseller))
    with Indent(printer):
        merchant = get_merchant(parsed_args.merchant, parsed_args.target, printer=printer)
        if merchant:
            reseller = get_reseller(parsed_args.reseller, parsed_args.target, printer=printer)
            if reseller:
                set_merchant_reseller(merchant, parsed_args.target, reseller, printer=printer)
    printer("OK")

def print_new_merchant():

    parsed_args = parse(Parseable.region, Parseable.reseller, Parseable.partner_control_match_criteria, Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Creating New Merchant")
    with Indent(printer):
        if parsed_args.partnercontrolmatchcriteria:
            reseller = get_reseller(parsed_args.reseller, parsed_args.target, and_channels=False, printer=printer)
            reseller.channel = {}
            reseller.channel.update(parsed_args.partnercontrolmatchcriteria)
        else:
            reseller = get_reseller(parsed_args.reseller, parsed_args.target, and_channels=True, printer=printer)
        uid = create_merchant(parsed_args.target, parsed_args.region, reseller, printer=printer)
        merchant = get_merchant(uid, parsed_args.target, printer=printer)

    if merchant:
        print(merchant)

def get_plan_groups(target, printer=StatusPrinter()):

    endpoint = '{}://{}:{}/v3/merchant_plan_groups'.format(
                target.get_hypertext_protocol(),
                target.get_hostname(),
                target.get_http_port())

    headers = { 'Accept' : '*/*',
                'Cookie' : internal_auth(target, printer=printer) }

    response = get(endpoint, headers, printer=printer)

    plan_group_dict = json.loads(response.content.decode('utf-8'))

    return plan_group_dict

def print_plan_groups():

    parsed_args = parse(Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Getting plan groups according to {}".format(parsed_args.target.get_name()))
    with Indent(printer):
        plan_groups_dict = get_plan_groups(parsed_args.target, printer=printer)

    output = json.dumps(plan_groups_dict['elements'])

    printer('')
    print_or_warn(output, max_length=500)

# given a plan group id or a plan group uuid, get the group
def get_plan_group(plan_group, target, printer=StatusPrinter()):
    printer("Finding plan_group {} according to {}".format(plan_group, target.get_name()))
    with Indent(printer):
        if is_uuid(plan_group):
            ident='uuid'
        else:
            ident='id'

        q = Query(target, 'metaRO', 'test321',
                """
                SELECT id as db_id, uuid as id, name, enforce_assignment, trial_days
                FROM merchant_plan_group
                WHERE {} = '{}';
                """.format(ident, plan_group))

        plan_group = q.execute(Feedback.OneRow, lambda row : PlanGroup(row), printer=printer)

    if not plan_group:
        printer("this plan group does not exist on {}".format(target.get_name()))

    return plan_group

def print_plan_group():

    parsed_args = parse(Parseable.plan_group, Parseable.target)
    printer = StatusPrinter(indent=0)

    try:
        plan_group = get_plan_group(parsed_args.plangroup, parsed_args.target, printer=printer)
        print(plan_group)

    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def create_plan_group(name, target, trial_days=None, enforce_plan_assignment=False , printer=StatusPrinter()):
    printer("Creating a plan_group {} on {}".format(name, target.get_name()))
    with Indent(printer):

        path='v3/merchant_plan_groups'

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json ',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        data = { "name"              : name,
                 "enforceAssignment" : enforce_plan_assignment,
                 "trialDays"         : trial_days }

        response = post(endpoint, headers, data, printer=printer)
        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

        return json.loads(response.content.decode('utf-8'))


def print_new_plan_group():

    parsed_args = parse(Parseable.name, Parseable.trial_days, Parseable.enforce_plan_assignment, Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Creating a plan group on {}".format(parsed_args.target.get_name()))
    with Indent(printer):
        plan_groups_dict = create_plan_group(parsed_args.name,
                                             parsed_args.target,
                                             trial_days=parsed_args.trialdays,
                                             enforce_plan_assignment=parsed_args.enforceplanassignment,
                                             printer=printer)

    output = str(get_plan_group(plan_groups_dict['id'], parsed_args.target))
    printer('')
    print_or_warn(output, max_length=500)

# given a merchant_plan id or a merchant_plan uuid, get the database entry
def get_plan(plan, target, printer=StatusPrinter(), identifiers_only=False):
    printer("Finding plan {}'s identifiers according to {}".format(plan, target.get_name()))
    with Indent(printer):
        if is_uuid(plan):
            ident='uuid'
        else:
            ident='id'

        q = Query(target, 'metaRO', 'test321',
                """
                SELECT id as db_id, uuid as id, merchant_plan_group_id
                FROM merchant_plan
                WHERE {} = '{}';
                """.format(ident, plan))

        plan = q.execute(Feedback.OneRow, lambda row : Plan(row), printer=printer)

    if identifiers_only:
        return plan

    plan_group = get_plan_group(plan.merchantPlanGroup_db_id, target, printer=printer)

    printer("Getting plan {} from {}".format(plan, target.get_name()))
    with Indent(printer):

        path='v3/merchant_plan_groups/{}/merchant_plans/{}'.format(
            plan_group.id, plan.id)

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json ',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        response = get(endpoint, headers, printer=printer)
        if response.status_code < 200 or response.status_code > 299:
            raise Exception("GET on {} returned code {}".format(endpoint, response.status_code))

        plan.apply_response(json.loads(response.content.decode('utf-8')))

        return plan

def print_get_plan():

    parsed_args = parse(Parseable.plan, Parseable.target)
    printer = StatusPrinter(indent=0)

    try:
        plan = get_plan(parsed_args.plan, parsed_args.target, printer=printer)
        printer('')
        print_or_warn(str(plan), max_length=500)

    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def warn_if_mismatched(item_name, item_val, key, the_dict, prefer='provided', printer=StatusPrinter()):
    try:
        print(the_dict)
        if item_val != the_dict[key]:
            printer("provided {} ({}) mismatches encoded {} ({})\n"
                                .format(item_name,
                                        item_val,
                                        key,
                                        the_dict[key])
                    + "preferring {} version".format(prefer))
    except KeyError:
        pass

def new_plan(plan_dict, target, printer=StatusPrinter()):

    printer("[Creating a plan from supplied json]")
    with Indent(printer):

        try:
            path='v3/merchant_plan_groups/{}/merchant_plans'.format(plan_dict['merchantPlanGroup']['id'])
        except KeyError as e:
            printer(textwrap.dedent(
                """
                Error: Plan json must specify the plan group, like so:
                     {
                       "name": "Foo Plan"
                       "description": "I'm a plan",
                       "merchantPlanGroup": {
                         "id": "SOMEPLANGROUPUUID"
                       }
                     }
                """).strip())
            raise e

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }


        data = plan_dict

        response = post(endpoint, headers, data, printer=printer)

        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

        return json.loads(response.content.decode('utf-8'))

def print_new_plan():

    parsed_args = parse(Parseable.plan_dict, Parseable.target)
    printer = StatusPrinter(indent=0)

    if 'db_id' in parsed_args.plandict or 'id' in parsed_args.plandict:
        raise Exception("Plan description has a db_id or an id, can't create it if it already exists\n"
                        "Maybe try set_plan ?")

    result = new_plan(parsed_args.plandict, parsed_args.target, printer=printer)

    print(json.dumps(result))

def set_plan(plan_dict, target, printer=StatusPrinter()):

    printer("[Updating plan from supplied json]")
    with Indent(printer):

        try:
            path='v3/merchant_plan_groups/{}/merchant_plans/{}'.format(
                plan_dict['merchantPlanGroup']['id'],
                plan_dict['id']
            )
        except KeyError as e:
            printer(textwrap.dedent(
                """
                Error: Plan json must specify the plan group, like so:
                     {
                       "name": "Foo Plan"
                       "description": "I'm a plan",
                       "merchantPlanGroup": {
                         "id": "SOMEPLANGROUPUUID"
                       }
                     }
                """).strip())
            raise e

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }


        data = plan_dict

        response = put(endpoint, headers, data, printer=printer)

        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

        return json.loads(response.content.decode('utf-8'))

def print_set_plan():

    parsed_args = parse(Parseable.plan_dict, Parseable.target)
    printer = StatusPrinter(indent=0)

    if 'id' in parsed_args.plandict:
        plan = get_plan(parsed_args.plandict['id'], parsed_args.target, printer)
    elif 'db_id' in parsed_args.plandict:
        plan = get_plan(parsed_args.plandict['db_id'], parsed_args.target, printer)
        parsed_args.plandict['id'] = plan.id
    else:
        printer(textwrap.dedent(
            """It is not clear which plan you want to update, maybe try new_plan?
               Otherwise, specify either 'db_id' or 'id' (uuid) in the json, like so:
                 {
                   "id" : "SOMEPLANUUID"
                   "name" : "Foo Plan"
                   "description" : "I'm a plan",
                 }
            """).strip())
        raise ValueError("Missing Required Data")


    result = set_plan(parsed_args.plandict, parsed_args.target, printer=printer)

    print(result)

def get_partner_controls(target, printer=StatusPrinter()):

    endpoint = '{}://{}:{}/v3/partner_controls'.format(
                target.get_hypertext_protocol(),
                target.get_hostname(),
                target.get_http_port())

    headers = { 'Accept' : '*/*',
                'Cookie' : internal_auth(target, printer=printer) }

    response = get(endpoint, headers, printer=printer)

    partner_controls = json.loads(response.content.decode('utf-8'))

    return partner_controls

def print_partner_controls():

    parsed_args = parse(Parseable.target)
    printer = StatusPrinter(indent=0)

    printer("Getting partner controls according to {}".format(parsed_args.target.get_name()))
    with Indent(printer):
        partner_controls_dict = get_partner_controls(parsed_args.target, printer=printer)

    output = json.dumps(partner_controls_dict['elements'])

    printer('')
    print_or_warn(output, max_length=500)

def get_partner_control(partner_control, target, printer=StatusPrinter(), identifiers_only=False):
    printer("Finding partner_control {}'s identifiers according to {}".format(partner_control, target.get_name()))
    with Indent(printer):
        if is_uuid(partner_control):
            ident='uuid'
        else:
            ident='id'

        q = Query(target, 'metaRO', 'test321',
                """
                SELECT id as db_id, uuid as id
                FROM partner_control
                WHERE {} = '{}';
                """.format(ident, partner_control))

        partner_control = q.execute(Feedback.OneRow, lambda row : PartnerControl(row), printer=printer)

    if identifiers_only:
        return partner_control

    printer("Getting partner control {} from {}".format(partner_control, target.get_name()))
    with Indent(printer):

        path='v3/partner_controls/{}'.format(partner_control.id)

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json ',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        response = get(endpoint, headers, printer=printer)
        if response.status_code < 200 or response.status_code > 299:
            raise Exception("GET on {} returned code {}".format(endpoint, response.status_code))

        partner_control.apply_response(json.loads(response.content.decode('utf-8')))

        return partner_control

def print_get_partner_control():

    parsed_args = parse(Parseable.partner_control, Parseable.target)
    printer = StatusPrinter(indent=0)

    try:
        partner_control = get_partner_control(parsed_args.partnercontrol, parsed_args.target, printer=printer)
        printer('')
        print_or_warn(str(partner_control), max_length=500)

    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)


def create_partner_control(partner_control_dict, target, printer=StatusPrinter()):

    printer("[Creating a partner control from supplied json]")
    with Indent(printer):

        path='v3/partner_controls'

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }


        data = partner_control_dict

        response = post(endpoint, headers, data, printer=printer)

        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

        return json.loads(response.content.decode('utf-8'))


def print_new_partner_control():
    parsed_args = parse(Parseable.partner_control_dict, Parseable.target)
    printer = StatusPrinter(indent=0)

    if 'db_id' in parsed_args.partnercontroldict or 'id' in parsed_args.partnercontroldict:
        raise Exception("Partner control description has a db_id or an id, can't create it if it already exists\n"
                        "Maybe try set_partner_control ?")

    result = create_partner_control(parsed_args.partnercontroldict, parsed_args.target, printer=printer)

    print(json.dumps(result))


def set_partner_control(partner_control_dict, target, printer=StatusPrinter()):

    printer("[Updating partner_control from supplied json]")
    with Indent(printer):

        path='v3/partner_controls/{}'.format(partner_control_dict['id'])

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        data = partner_control_dict

        response = put(endpoint, headers, data, printer=printer)

        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

        return json.loads(response.content.decode('utf-8'))

def print_set_partner_control():

    parsed_args = parse(Parseable.partner_control_dict, Parseable.target)
    printer = StatusPrinter(indent=0)

    if 'id' in parsed_args.partnercontroldict:
        partner_control = get_partner_control(parsed_args.partnercontroldict['id'], parsed_args.target, printer)
    elif 'db_id' in parsed_args.partnercontroldict:
        partner_control = get_partner_control(parsed_args.partnercontroldict['db_id'], parsed_args.target, printer)
        parsed_args.partnercontroldict['id'] = partner_control.id
    else:
        printer(textwrap.dedent(
            """It is not clear which partner control you want to update, maybe try new_partner_control?
               Otherwise, specify either 'db_id' or 'id' (uuid) in the json, like so:
                 {
                   "id" : "SOMEPLANUUID"
                   "name" : "Foo PartnerControl"
                   "description" : "I'm a partner control",
                 }
            """).strip())
        raise ValueError("Missing Required Data")


    result = set_partner_control(parsed_args.partnercontroldict, parsed_args.target, printer=printer)

    print(result)

def get_partner_control_plan(partner_control, target, printer=StatusPrinter()):

    printer("[Getting partner_control from supplied json]")
    with Indent(printer):

        path='v3/partner_controls/{}?expand=plan'.format(partner_control.id)

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        response = get(endpoint, headers, printer=printer)

        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

        return json.loads(response.content.decode('utf-8'))['plan']

def print_get_partner_control_plan():

    parsed_args = parse(Parseable.partner_control, Parseable.target)
    printer = StatusPrinter(indent=0)

    partner_control = get_partner_control(parsed_args.partnercontrol, parsed_args.target, printer=printer)

    result = get_partner_control_plan(partner_control, parsed_args.target, printer=printer)

    print(result)

def set_partner_control_plan(partner_control, plan, target, printer=StatusPrinter()):

    printer("[Setting partner_control to board to plan {}]".format(partner_control, plan))
    with Indent(printer):

        path='v3/partner_controls/{}/merchant_plan/{}'.format(partner_control.id, plan.id)

        endpoint = '{}://{}:{}/{}'.format(
                    target.get_hypertext_protocol(),
                    target.get_hostname(),
                    target.get_http_port(),
                    path)

        headers = { 'Content-Type' : 'application/json',
                          'Accept' : 'application/json, text/javascript, */*; q=0.01',
                      'Connection' : 'keep-alive',
                          'Cookie' : internal_auth(target, printer=printer) }

        response = post(endpoint, headers, {}, printer=printer)

        if response.status_code < 200 or response.status_code > 299:
            raise Exception("POST on {} returned code {}".format(endpoint, response.status_code))

def print_set_partner_control_plan():

    parsed_args = parse(Parseable.partner_control, Parseable.plan, Parseable.target)
    printer = StatusPrinter(indent=0)

    partner_control = get_partner_control(parsed_args.partnercontrol, parsed_args.target, printer=printer)

    plan = get_plan(parsed_args.plan, parsed_args.target, printer=printer)

    set_partner_control_plan(partner_control, plan, parsed_args.target, printer=printer)
