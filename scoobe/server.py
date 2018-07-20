import sys
import os
import re
import json
import textwrap
import datetime
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
    response = post(endpoint, headers, data, obfuscate_pass=True, printer=printer)

    if response.status_code == 200:
        return response.headers['set-cookie']

    # if that fails, use a real one
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



def is_uuid(string):
    if re.match(r'[A-Za-z0-9]{13}', str(string)):
        return True
    return False

# given a merchant id or a merchant uuid, get both
def get_merchant(merchant, target, printer=StatusPrinter()):

    class Merchant:
        def __init__(self, row):
            self.id = row['id']
            self.uuid = row['uuid']

        def __str__(self):
            return json.dumps(self.__dict__)

    if is_uuid(merchant):
        q = Query(target, 'metaRO', 'test321',
                """
                SELECT id, uuid
                FROM merchant
                WHERE uuid = '{}';
                """.format(merchant))
    else:
        q = Query(target, 'metaRO', 'test321',
                """
                SELECT id, uuid
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
        printer("Finding merchant {}'s identifiers according to {}".format(args.merchant, args.target.get_name()))
        with Indent(printer):
            merchant = get_merchant(args.merchant, args.target, printer=printer)
        print(merchant)

    except ValueError as ex:
        printer(str(ex))
        sys.exit(30)

# given a serial number and a server, get the merchant associated with that serial number on that server
def get_device_merchant(serial, target, printer=StatusPrinter()):

    q = Query(target, 'metaRO', 'test321',
            """
            SELECT merchant_id
            FROM device_provision
            WHERE serial_number = '{}';
            """.format(serial))

    merchant_id = q.execute(Feedback.OneRow, lambda row : row['merchant_id'], printer=printer)

    if not merchant_id:
        printer("this device is not associated with a merchant on {}".format(target.get_name()))

    return merchant_id


def print_device_merchant():

    args = parse(Arg.serial, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s merchant according to {}".format(args.serial, args.target.get_name()))
        with Indent(printer):
            merchant_id = get_device_merchant(args.serial, args.target, printer=printer)

        printer("Finding merchant {}'s UUID according to {}".format(merchant_id, args.target.get_name()))
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

    print_or_warn(output, max_length=500)

# returns the merchant currently associated with the specified device
Reseller = namedtuple('Reseller', 'id uuid name')

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


SetResult = namedtuple('SetResult', 'change_made description')
def describe_set_device_reseller(serial, target, target_reseller_id, printer=StatusPrinter()):

    printer("Checking the device's reseller")
    with Indent(printer):
        current_reseller = get_device_reseller(serial, target, printer)

    if not current_reseller:
        return SetResult(False, "Could not find reseller")

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

            rows_changed = q.execute(Feedback.ChangeCount, printer=printer)

            if rows_changed == 1:
                return SetResult(True, "NOTICE: the attached device's reseller has changed from {} to {}".format(
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
            SELECT id, uuid, name, parent_id
            FROM reseller
            WHERE id = (SELECT reseller_id
                        FROM merchant
                        WHERE uuid = '{}');
            """.format(merchant_uuid))

    reseller = q.execute(Feedback.OneRow, lambda row : Reseller(row), printer=printer)

    if not reseller:
        printer("This merchant is not associated with a reseller according to {}".format(target.get_name()))

    return reseller

def print_merchant_reseller():

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter(indent=0)

    try:
        printer("Finding {}'s reseller according to {}".format(args.merchant, args.target.get_name()))
        with Indent(printer):
            reseller = get_merchant_reseller(args.merchant, args.target, printer=printer)
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

    return code

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

    printer("Checking Acceptedness Code")
    with Indent(printer):
        merchant_id = get_merchant(args.merchant, args.target)['id']

        acceptedness = get_acceptedness(args.target, merchant_id, printer=printer)

    print(acceptedness)

def set_acceptedness(target, merchant_id, value, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE setting SET value = {}
            WHERE merchant_id = {} AND name = 'ACCEPTED_BILLING_TERMS';
             """.format(value, merchant_id, serial))

    rows_changed = q.run_get_rows_changed(printer=printer)
    if rows_changed != 1:
        raise ValueError("Expected 1 change to device_provision, instead got {}".format(rows_changed))

def set_activation_code(target, serial, value, printer=StatusPrinter()):

    q = Query(target, 'metaRW', 'test789',
            """
            UPDATE device_provision SET activation_code = {}
            WHERE serial_number = '{}';
             """.format(value, serial))

    rows_changes = q.execute(Feedback.ChangeCount, printer=printer)

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

    def get(row):
        val = row['last_activation_code']
        if val:
            return int(val)
        else:
            return None

    return q.get_from_first_row(get, printer=printer)

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

    args = parse(Arg.serial, Arg.target)
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

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter(indent=0)
    printer("Clearing Terms Acceptance")

    with Indent(printer):

        desired_value = '\'0\''
        # yes, that's the string containing 0
        # word on the street is that it's better than 0 or null

        printer("Checking Acceptedness")
        with Indent(printer):
            accepted = get_acceptedness(args.target, args.merchant, printer=printer)

        if accepted == desired_value.strip('\''):
            printer("Already cleared, no change needed")
        else:
            printer("Revoking Acceptedness")
            with Indent(printer):
                set_acceptedness(args.target, args.merchant, desired_value, printer=printer)
    printer("OK")

def accept():

    args = parse(Arg.merchant, Arg.target)
    printer = StatusPrinter()
    printer("Accepting Terms")

    set_acceptedness(args.target, args.merchant, "1")

    new_val = get_acceptedness(args.target, args.merchant)
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

        response = put(endpoint, headers, printer=printer, data={})

    # TODO: server/scripts/disassociate_device.py also DELETEs '/v3/resellers/{rId}/devices/{serial}'
    # maybe this function should do that also?

    if response.status_code == 200:
        printer('OK')
    else:
        printer('Error')
        sys.exit(10)

# provision device for merchant
def provision():

    args = parse(Arg.serial, Arg.target, Arg.merchant, Arg.cpuid)
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
                args.target.get_hostname() + ":" + str(args.target.get_http_port()),
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

def create_merchant(target, reseller, printer=StatusPrinter()):

    unique_str = str(datetime.datetime.utcnow().strftime('%s'))
    merchant_str = "merchant_" + unique_str
    mid = int(unique_str)
    bemid = 8000000000 - mid


    base_message = textwrap.dedent(
    """
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
	<Email>{merchant_str}@.com</Email>
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
    """.format(**locals()))

    endpoint = '{}://{}:{}/cos/v1/partner/fdc/create_merchant'.format(
                target.get_hypertext_protocol(),
                target.get_hostname(),
                target.get_http_port())

    headers = { 'Content-Type' : 'text/plain',
                      'Accept' : '*/*',
                      'Cookie' : internal_auth(target, printer=printer)}

    data = base_message

    response = post(endpoint, headers, data, printer=printer)



    return response

def print_new_merchant():

    args = parse(Arg.target, Arg.reseller)
    printer = StatusPrinter(indent=0)
    printer("Creating New Merchant")
    with Indent(printer):
        uid = create_merchant(args.target, args.reseller, printer=printer)
        import IPython
        IPython.embed()
    print(uid)

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
                args.target.get_hostname() + ":" + str(args.target.get_http_port()),
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
