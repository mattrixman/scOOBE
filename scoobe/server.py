import sys
import os
import re
import json
import textwrap
import datetime
import xmltodict
import pprint as pp
from collections import namedtuple, OrderedDict
import xml.etree.ElementTree as ET
from argparse import ArgumentParser
from scoobe.cli import parse, print_or_warn, Parsable as Arg
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
    args = parse(Arg.target)
    printer = StatusPrinter(indent=0)

    printer("Getting a login cookie from {}".format(args.target.get_name()))
    with Indent(printer):
        cookie = internal_auth(args.target, printer=printer)

    if cookie:
        print(cookie)



def is_uuid(string):
    if re.match(r'[A-Za-z0-9]{13}', str(string)):
        return True
    return False

class Merchant:
    def __init__(self, row):
        self.id = row['id']
        self.uuid = row['uuid']
        self.reseller_id = row['reseller_id']

    def __str__(self):
        return json.dumps(self.__dict__)

# given a merchant id or a merchant uuid, get both
def get_merchant(merchant, target, printer=StatusPrinter()):

    printer("Finding merchant {}'s identifiers according to {}".format(merchant, target.get_name()))
    with Indent(printer):
        if is_uuid(merchant):
            q = Query(target, 'metaRO', 'test321',
                    """
                    SELECT id, uuid, reseller_id
                    FROM merchant
                    WHERE uuid = '{}';
                    """.format(merchant))
        else:
            q = Query(target, 'metaRO', 'test321',
                    """
                    SELECT id, uuid, reseller_id
                    FROM merchant
                    WHERE id = {};
                    """.format(merchant))

        merchant = q.execute(Feedback.OneRow, lambda row : Merchant(row), printer=printer)

    if not merchant:
        printer("this merchant does not exist on {}".format(target.get_name()))

    return merchant

def print_merchant():

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        merchant = get_merchant(args.merchant, args.target, printer=printer)
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

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s merchant according to {}".format(args.serial, args.target.get_name()))
        with Indent(printer):
            merchant_id = get_device_merchant_id(args.serial, args.target, printer=printer)

        printer("Finding merchant {}'s identifiers according to {}".format(merchant_id, args.target.get_name()))
        with Indent(printer):
            merchant = get_merchant(merchant_id, args.target, printer=printer)
        print(merchant)

    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

def get_resellers(target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id, uuid, name, parent_id FROM reseller order by id;
            """)

    def as_dict(x):
        return {x['id'] : { 'uuid' : x['uuid'], 'name' : x['name'], 'parent_id' : x['parent_id']}}


    row_dicts = q.execute(Feedback.ManyRows, as_dict, print_transform = True, printer=printer)

    reseller_dict = {}
    for row_dict in row_dicts:
        reseller_dict.update(row_dict)

    return reseller_dict

def print_resellers():

    args = parse(Arg.target)
    printer = StatusPrinter(indent=0)

    printer("Getting resellers according to {}".format(args.target.get_name()))
    with Indent(printer):
        resellers_dict = get_resellers(args.target, printer=printer)

    output = json.dumps(resellers_dict)

    printer('')
    print_or_warn(output, max_length=500)

class Reseller:
    def __init__(self, row):
        self.id = row['id']
        self.uuid = row['uuid']
        self.name = row['name']
        self.parent_id = row['parent_id']

def get_device_reseller(serial, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT id, uuid, name, parent_id
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

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(args.serial, args.target.get_name()))
        with Indent(printer):
            reseller = get_device_reseller(args.serial, args.target, printer=printer)
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
        current_reseller = Reseller({'id' : 999999, 'uuid' : 'NONE', 'name' : 'NONE', 'parent_id' : 999999})

    # don't modify if desired value is already set
    if int(current_reseller.id) == int(target_reseller.id):
        printer("The device's current reseller is the same as the target reseller ({}). Making no change."
                                .format(target_reseller.id))
        return True

    # otherwise modify
    else:
        printer("Changing the device's reseller: {} -> {}".format(current_reseller.id, target_reseller.id))
        with Indent(printer):

            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE device_provision
                    SET reseller_id = {}
                    WHERE serial_number = '{}';
                    """.format(target_reseller.id, serial))

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)

            if rows_changed == 1:
                printer("NOTICE: the attached device's reseller has changed from {} to {}".format(
                                        current_reseller.id, target_reseller.id))
                return True
            else:
                raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def get_reseller(reseller, target, printer=StatusPrinter()):

    printer("Finding reseller {}'s identifiers according to {}".format(reseller, target.get_name()))
    with Indent(printer):

        if is_uuid(reseller):
            q = Query(target, 'metaRO', 'test321',
                    """
                    SELECT id, uuid, name, parent_id
                    FROM reseller
                    WHERE uuid = '{}';
                    """.format(reseller))
        else:
            q = Query(target, 'metaRO', 'test321',
                    """
                    SELECT id, uuid, name, parent_id
                    FROM reseller
                    WHERE id = {};
                    """.format(reseller))

    reseller = q.execute(Feedback.OneRow, lambda row : Reseller(row), printer=printer)

    if not reseller:
        printer("No such reseller found on {}".format(target.get_name()))

    return reseller

def print_set_device_reseller():

    args = parse(Arg.serial, Arg.target, Arg.reseller)
    printer = StatusPrinter(indent=0)

    printer("Setting device: {}'s reseller to {}".format(args.serial, args.reseller))
    with Indent(printer):
        reseller = get_reseller(args.reseller, args.target, printer=printer)
        if reseller:
            set_device_reseller(args.serial, args.target, reseller, printer=printer)
    printer("OK")

def print_merchant_reseller():

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        merchant = get_merchant(args.merchant, args.target, printer=printer)

        printer("Finding {}'s reseller according to {}".format(merchant.uuid, args.target.get_name()))
        with Indent(printer):
            reseller = get_reseller(merchant.reseller_id, args.target, printer=printer)
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

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)
    printer("Getting Activation Code")

    with Indent(printer):
        print(get_activation_code(args.target, args.serial, printer=printer))

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

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter(indent=0)

    merchant = get_merchant(args.merchant, args.target)

    printer("Checking Acceptedness Code")
    with Indent(printer):
        acceptedness = get_acceptedness(args.target, merchant.id, printer=printer)

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

    args = parse(Arg.serial, Arg.target, Arg.code)
    printer = StatusPrinter(indent=0)

    printer("Setting Activation Code to {}".format(args.code))
    with Indent(printer):
        set_activation_code(args.target, args.serial, args.code, printer=printer)

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

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)

    printer("Refreshing Activation Code")
    with Indent(printer):

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

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter(indent=0)
    printer("Clearing Terms Acceptance")

    with Indent(printer):

        merchant = get_merchant(args.merchant, args.target, printer=printer)

        printer("Revoking Acceptedness")
        with Indent(printer):
            set_acceptedness(args.target, merchant.id, "0", printer=printer)

    printer("OK")

def accept():

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter()


    printer("Accepting Terms")
    with Indent(printer):

        merchant = get_merchant(args.merchant, args.target, printer=printer)

        set_acceptedness(args.target, merchant.id, "1")

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

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)
    printer("Deprovisioning Device")
    with Indent(printer):

        try:

            printer("Finding device {}'s merchant according to {}".format(args.serial, args.target.get_name()))
            with Indent(printer):
                merchant_id = get_device_merchant_id(args.serial, args.target, printer=printer)

            printer("Getting the deprovision auth token according to {}".format(args.target.get_name()))
            with Indent(printer):
                auth_token = get_auth_token(args.target,
                        '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/deprovision')

            printer("Requesting that {} deprovision the device".format(args.target.get_name()))
            with Indent(printer):

                merchant = get_merchant(merchant_id, args.target, printer=printer)

                endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/deprovision'.format(
                            args.target.get_hypertext_protocol(),
                            args.target.get_hostname() + ":" + str(args.target.get_http_port()),
                            merchant.uuid,
                            args.serial)

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

    args = parse(Arg.serial, Arg.cpuid, Arg.target, Arg.merchant)
    printer = StatusPrinter(indent=0)
    printer("Provisioning Device")
    with Indent(printer):

        printer("Checking Merchant Reseller")
        with Indent(printer):
            merchant = get_merchant(args.merchant, args.target, printer=printer)
            merchant_reseller = get_reseller(merchant.reseller_id, args.target, printer=printer)

        printer("Ensuring device/merchant resellers match")
        with Indent(printer):

            try:
                success = set_device_reseller(args.serial, args.target, merchant_reseller, printer=printer)
            except ValueError as err:
                if "not associated" in str(err):
                    printer("Device not provisioned, so no conflicting reseller exists")
                    success = True

            # only proceed to provision if target merchant's reseller doesn't conflict
            if not success:
                sys.exit(313)

        printer("Getting provision endpoint auth token")
        with Indent(printer):
            auth_token = get_auth_token(args.target,
                    '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision',
                    printer=printer)

        printer("Provisioning device to merchant")
        with Indent(printer):

            endpoint = '{}://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                    args.target.get_hypertext_protocol(),
                    args.target.get_hostname() + ":" + str(args.target.get_http_port()),
                    merchant.uuid,
                    args.serial)

            headers = {'Authorization' : 'Bearer ' + auth_token }

            data = { 'merchantUuid': merchant.uuid,
                     'serial': args.serial,
                     'chipUid': args.cpuid }

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
    <Sys-Prin>/</Sys-Prin>
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
    <BankMarker>123</BankMarker>
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
    <Agent>1</Agent>
    <Chain>846217707000</Chain>
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
               <CloseMethod/><SerialNumber/><CloverVersion/><Status>Active</Status><BundleIndicator>P03</BundleIndicator>
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
      <email>matt.rixman+2019-02-20@clover.com</email>
    </contactInformation>
    <reseller>FDMS-NGPOS</reseller>
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

def create_merchant(target, reseller, printer=StatusPrinter()):

    unique_str = str(datetime.datetime.utcnow().strftime('%s'))
    merchant_str = "merchant_" + unique_str
    mid = int(unique_str)
    bemid = 8000000000 - mid

    # path=eu_path
    # template=eu_xml

    path=us_path
    template=us_xml

    xml=template.format(**locals())

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
    response_dict = xmltodict.parse(response.content.decode('utf-8'))
    return response_dict['XMLResponse']['Merchant']['UUID']

# return true if desired state is achieved
# whether or not this function made a change
def set_merchant_reseller(merchant, target, target_reseller, printer=StatusPrinter()):

    printer("Checking the merchant's current reseller")
    with Indent(printer):
        current_reseller = get_reseller(merchant.reseller_id, target, printer)

    # don't modify if desired value is already set
    if int(current_reseller.id) == int(target_reseller.id):
        printer("The merchant's current reseller is the same as the target reseller ({}). Making no change."
                                .format(target_reseller.id))
        return True

    # otherwise modify
    else:
        printer("Changing the merchnat's reseller: {} -> {}".format(current_reseller.id, target_reseller.id))
        with Indent(printer):

            q = Query(target, 'metaRW', 'test789',
                    """
                    UPDATE merchant
                    SET reseller_id = {}
                    WHERE id = '{}';
                    """.format(target_reseller.id, merchant.id))

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)

            if rows_changed == 1:
                printer("NOTICE: the merchant's reseller has changed from {} to {}".format(
                    current_reseller.id, target_reseller.id))
                return True
            else:
                raise ValueError("Expected 1 change to merchant, instead got {}".format(rows_changed))

def print_set_merchant_reseller():

    args = parse(Arg.merchant, Arg.target, Arg.reseller)
    printer = StatusPrinter(indent=0)

    printer("Setting the merchant's reseller to {}".format(args.reseller))
    with Indent(printer):
        merchant = get_merchant(args.merchant, args.target, printer=printer)
        if merchant:
            reseller = get_reseller(args.reseller, args.target, printer=printer)
            if reseller:
                set_merchant_reseller(merchant, args.target, reseller, printer=printer)
    printer("OK")

def print_new_merchant():

    args = parse(Arg.target, Arg.reseller)
    printer = StatusPrinter(indent=0)
    printer("Creating New Merchant")
    with Indent(printer):
        uid = create_merchant(args.target, args.reseller, printer=printer)
        merchant = get_merchant(uid, args.target, printer=printer)

    printer("Setting Merchant Reseller")
    with Indent(printer):
        if merchant:
            printer("Target Reseller")
            reseller = get_reseller(args.reseller, args.target)
            if reseller:
                set_merchant_reseller(merchant, args.target, reseller)

    if merchant:
        print(uid)

def get_plan_groups(target, printer=StatusPrinter()):

    endpoint = '{}://{}:{}/v3/merchant_plan_groups'.format(
                target.get_hypertext_protocol(),
                target.get_hostname(),
                target.get_http_port())

    headers = { 'Accept' : '*/*',
                'Cookie' : internal_auth(target, printer=printer)}

    response = get(endpoint, headers, printer=printer)

    plan_group_dict = json.loads(response.content.decode('utf-8'))

    return plan_group_dict

def print_plan_groups():

    args = parse(Arg.target)
    printer = StatusPrinter(indent=0)

    printer("Getting plan groups according to {}".format(args.target.get_name()))
    with Indent(printer):
        plan_groups_dict = get_plan_groups(args.target, printer=printer)

    output = json.dumps(plan_groups_dict)

    printer('')
    print_or_warn(output, max_length=500)
