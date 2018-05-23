import sh
from time import sleep
import sys
import _mysql
import socket
import sshconf
import re
import requests
import json
from collections import namedtuple
from sh import ErrorReturnCode_1
from os.path import expanduser, join
from sshconf import read_ssh_config
from argparse import ArgumentParser
from textwrap import indent, dedent

# print status to stderr so only desired value is written to stdout
# default to a four-space indent
def printstatus(msg, extra_indent=0):
    print(indent(msg.__str__(), '    ' + ' ' * extra_indent), file=sys.stderr)

# encapsulates the local ssh config entry for a particular host
class SshConfig:
    def __init__(self, host):
        try:
            # Read the local ssh config
            configs = read_ssh_config(join(expanduser('~'),'.ssh','config'))
            if host not in configs.hosts():
                raise ValueError("{} not configured in ~/.ssh/config".format(host))
            config = configs.host(host)


            # initialize fields on the object with entries in the ssh config
            self.__dict__.update(config)

            # also find the local port which is forwarded to the remote mysql daemon
            self.mysql_port = SshConfig.mysql_port(config)

            # and include the config section name
            self.ssh_host = host

        except Exception as ex:
            print(ex, "Do you have your ~/.ssh/config set up to forward a local port to 3306 on {}? ".format(host) +
                   "If not, see https://confluence.dev.clover.com/pages/viewpage.action?pageId=20711161",
                   file=sys.stderr)
            raise ex

    # given an ssh config entry, get whichever local port forwards to remote port 3306
    def mysql_port(config_section):

        # <local_port> <host>:<remote_port>
        # 10002 127.0.0.1:3306
        HasPort = namedtuple('HasPort', 'is_mysql local_port')
        def try_get_local_port(forward_str):
            m = re.match(r'(\d*) .*.*3306.*', forward_str)
            if m:
                return HasPort(True, int(m.group(1)))
            else:
                return HasPort(False, None)

        port = -1
        try:
            forwards = config_section['localforward']
        except KeyError:
            raise ValueError("{} has no port forwarding in ~/.ssh/config".format(config_entry))

        # if just one port is forwarded, see if the to-port targets mysql
        if isinstance(forwards, str):
            f = try_get_local_port(forwards)
            if f .is_mysql:
                port = f.local_port

        # if multiple ports are forwarded, take the first to-port that targets mysql
        else:
            port = next(f.local_port for f in map(try_get_local_port, forwards) if f.is_mysql)

        # it should be a real port
        assert(port > 0)
        assert(port < 65536)

        return port

# encapsulates an ssh session, which holds the tunnel open
class SshTunnel:

    class NullDevice:
        def write(self, s):
            pass

    def qprint(self, message, end='\n'):
        if not self.quiet:
            print(message, file=sys.stderr, end=end)

    def __init__(self, config, quiet=True, indent=''):
        self.quiet = quiet
        self.indent = indent

        # not a true hostname, this is the alias ssh config uses for each config entry
        self.host = config.ssh_host

        self.mysql_port = config.mysql_port

        if port_open(self.mysql_port):
            raise OSError("The local port ({}) you're trying to forward is already open.  ".format(self.mysql_port) +
                            "Close it first.")

        self.process = sh.ssh(self.host, _bg=True)

    def __enter__(self):
        connected = False

        # wait for connection to come up
        self.qprint(self.indent + 'connecting to ' + self.host, end='')
        while not connected:
            self.qprint('.', end='')
            connected = port_open(self.mysql_port)
            sleep(1)
        self.qprint('done')
        return self

    def __exit__(self, type, value, traceback):
        orig_stderr = sys.stderr
        try:
            sys.stderr = SshTunnel.NullDevice()
            self.process.terminate()
        except sh.ErrorReturnCode:
            pass

        # wait for connection to drop
        connected = True
        self.qprint(self.indent + 'disconnecting from ' + self.host, end='')
        while connected:
            self.qprint('.', end='')
            connected = port_open(self.mysql_port)
            sleep(1)
        self.qprint('done')

        sys.stderr = orig_stderr

# encapsulates a mysql query
class Query:
    def __init__(self, ssh_config, mysql_user, mysql_pass, sql):
        self.ssh_config = ssh_config
        self.mysql_user = mysql_user
        self.mysql_pass = mysql_pass
        self.sql = sql
        self._empty_message = "Expected a nonempty result for Query: " + sql

    def on_empty(self, message):
        self._empty_message = message

    # called externally when the user doesn't need to read data
    # called internally, parameter will be called with post-query connection string
    def execute(self, then=lambda db : None):
        # open an ssh tunnel
        with SshTunnel(self.ssh_config, quiet=False, indent='    ') as tun:
            # open a mysql connection
            db = _mysql.connect(user=self.mysql_user,
                                host='127.0.0.1',
                                port=tun.mysql_port,
                                db='meta',
                                passwd=self.mysql_pass)

            # show the query then run it
            printstatus("query:")
            printstatus(
                    indent(
                        dedent(self.sql).strip(),
                        '    '))
            db.query(self.sql)

            # do what the caller wanted
            return then(db)

    def get_from_first_row(self, getter):
        def get_row_val(db):
            row = db.store_result().fetch_row(how=1)
            if not row:
                printstatus("...got empty result")
                raise ValueError(self._empty_message)
            else:
                try:
                    printstatus("result:")
                    # if we're selecting rows directly
                    if isinstance(row, tuple):
                        printstatus(row[0], extra_indent=4)
                        return getter(row[0])
                    # if we're selecting the output of a mysql builtin
                    else:
                        printstatus(row, extra_indent=4)
                        return getter(row)
                except:
                    printstatus("Result:")
                    printstatus(row[0], extra_indent=4)
                    raise

        row = self.execute(then=get_row_val)

        return row

# returns true if the specified port is open on the local machine
def port_open(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1',port))
    sock.close()
    return result == 0

# grab the serial number and ssh config from the command line
SerialSsh = namedtuple('SerialSsh', 'serial_num ssh_config')
def parse_serial_ssh():
    parser = ArgumentParser()
    parser.add_argument("serial_num", type=str)
    parser.add_argument("ssh_config_host", type=str, help="ssh config entry name")
    args = parser.parse_args()

    if not re.match(r'C[A-Za-z0-9]{3}[UE][CQNOPRD][0-9]{8}', args.serial_num):
       raise ValueError("{} doesn't look like a serial number".format(args.serial_num))

    ssh_config = SshConfig(args.ssh_config_host)

    return SerialSsh(args.serial_num, ssh_config)

# returns the merchant currently associated with the specified device
Merchant = namedtuple('Merchant', 'id uuid')
def get_merchant(serial_num, ssh_config):
    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT id, uuid FROM merchant WHERE id = (SELECT merchant_id FROM device_provision WHERE serial_number = '{}');
            """.format(serial_num))

    q.on_empty("this device is not associated with a merchant on {}".format(ssh_config.ssh_host))

    return q.get_from_first_row(lambda row: Merchant(row['id'], row['uuid']))

# prints a json dictionary { "id" : "the_mid", "uuid" : "the_uuid" }
def print_merchant():
    args = parse_serial_ssh()
    merchant = get_merchant(args.serial_num, args.ssh_config)
    print(merchant._asdict())

def print_activation_code():
    args = parse_serial_ssh()
    print(get_activation_code(args.ssh_config, args.serial_num))

def get_activation_code(ssh_config, serial_num):

    q = Query(ssh_config, 'metaRO', 'test321',
            """
            SELECT activation_code FROM device_provision WHERE serial_number = '{}';
            """.format(serial_num))

    q.on_empty("This device is not known to {}".format(ssh_config.ssh_host))

    return int(q.get_from_first_row(lambda row: row['activation_code'].decode('utf-8')))

def get_acceptedness(ssh_config, serial_num):
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
    value = q.get_from_first_row(lambda row: row['value'])
    if value is None:
        return None
    else:
        return value.decode('utf-8')

def set_acceptedness(ssh_config, serial_num, value):
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
    print("Clearing Terms Acceptance", file=sys.stderr)
    set_acceptedness(args.ssh_config, args.serial_num, "NULL")

    new_val = get_acceptedness(args.ssh_config, args.serial_num)
    if new_val is None:
        print("OK", file=sys.stderr)
    else:
        raise ValueError("Failed to set acceptedness to {}.  Final value: {}".format("NULL", new_val))

def accept():
    args = parse_serial_ssh()
    print("Clearing Terms Acceptance", file=sys.stderr)
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
def print_mid():
    parser = ArgumentParser()
    parser.add_argument("ssh_config_host", type=str, help="ssh config entry name")
    parser.add_argument("merchant_uuid", type=str,
            help="the merchant uuid that we want a merchant id for")
    args = parser.parse_args()

    if not re.match(r'[A-Za-z0-9]{13}', args.merchant_uuid):
       raise ValueError("{} doesn't look like a merchant UUID".format(args.merchant_uuid))

    ssh_config = SshConfig(args.ssh_config_host)
    print(get_mid(ssh_config, args.merchant_uuid))

# deprovision device from merchant
def deprovision():
    print("Deprovisioning Device", file=sys.stderr)
    args = parse_serial_ssh()

    merchant_uuid = get_merchant(args.serial_num, args.ssh_config)

    auth_token = get_auth_token(args.ssh_config,
            '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/deprovision')


    endpoint = 'https:{}/v3/partner/pp/merchants/{}/devices/{}/deprovision'.format(
                args.ssh_config.hostname,
                merchant_uuid,
                args.serial_num)

    headers = { 'Authorization' : 'Bearer ' + auth_token }

    response = requests.put(endpoint, headers=headers)

    if response.status_code != 200:
        message = r._content.decode('utf-8')['message']
        if 'not associated' in message:
            print(message, file=sys.stderr)
        else:
            print(response.__dict__, file=sys.stderr)
    else:
        print('OK', file=sys.stderr)

# grab the serial number, cpuid, ssh config, and merchant from the command line
ProvisionArgs = namedtuple('ProvisionArgs', 'serial_num cpuid ssh_config merchant')
def parse_serial_ssh_merch():
    parser = ArgumentParser()
    parser.add_argument("serial_num", type=str)
    parser.add_argument("cpuid", type=str)
    parser.add_argument("ssh_config_host", type=str, help="ssh config entry name")
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
    print("Provisioning Device", file=sys.stderr)
    args = parse_serial_ssh_merch()

    auth_token = get_auth_token(args.ssh_config,
            '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision')

    'https://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
            args.ssh_config.hostname,
            args.merchant,
            args.serial_num)

    response = requests.put('https://{}/v3/partner/pp/merchants/{}/devices/{}/provision'.format(
                                args.ssh_config.hostname,
                                args.merchant,
                                args.serial_num),

                            headers = {'Authorization' : 'Bearer ' + auth_token },

                            data = {'mId': get_mid(args.ssh_config, args.merchant),
                                    'merchantUuid': args.merchant,
                                    'serial': args.serial_num,
                                    'chipUid': args.cpuid}
                           )

    if response.status_code != 200:
        message = r._content.decode('utf-8')['message']
        if 'not associated' in message:
            print(message, file=sys.stderr)
        else:
            print(response.__dict__, file=sys.stderr)
    else:
        print('OK', file=sys.stderr)

