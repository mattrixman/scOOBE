import sh
from time import sleep
import sys
import _mysql
import socket
import sshconf
import re
from collections import namedtuple
from sh import ErrorReturnCode_1
from os.path import expanduser, join
from sshconf import read_ssh_config
from argparse import ArgumentParser

def mysql_port(host):

    # extract the local port from a port-forwarding config entry
    #     example string:
    #     10002 127.0.0.1:3306
    #     <local_port> <host>:<remote_port>
    HasPort = namedtuple('HasPort', 'is_mysql local_port')
    def try_get_local_port(forward_str):
        m = re.match(r'(\d*) .*.*3306.*', forward_str)
        if m:
            return HasPort(True, int(m.group(1)))
        else:
            return HasPort(False, None)

    port = -1
    try:
        # Read the local ssh config
        configs = read_ssh_config(join(expanduser('~'),'.ssh','config'))
        if host not in configs.hosts():
            raise ValueError("Host not configured in ~/.ssh/config")
        config = configs.host(host)
        try:
            forwards = config['localforward']
        except KeyError:
            raise ValueError("{} has no port forwarding in ~/.ssh/config".format(host))

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

    except Exception as ex:
        print(ex, "Do you have your ~/.ssh/config set up to forward a local port to 3306 on {}? ".format(host) +
               "If not, see https://confluence.dev.clover.com/pages/viewpage.action?pageId=20711161")
        raise ex
    return port

def port_open(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1',port))
    sock.close()
    return result == 0

class SshTunnel:

    class NullDevice:
        def write(self, s):
            pass

    def __init__(self, host):
        self.host = host
        self.mysql_port = mysql_port(host)

        if port_open(self.mysql_port):
            raise Exception("The local port ({}) you're trying to forward is already open.  " +
                            "Close it first".format(self.mysql_port))

        self.process = sh.ssh(host, _bg=True)

    def __enter__(self):
        connected = False

        # wait for connection to come up
        print('connecting to ' + self.host, end='')
        while not connected:
            print('.', end='')
            connected = port_open(self.mysql_port)
            sleep(1)
        print('done')
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
        print('disconnecting from ' + self.host, end='')
        while connected:
            print('.', end='')
            connected = port_open(self.mysql_port)
            sleep(1)
        print('done')

        sys.stderr = orig_stderr

def get_merchant():
    parser = ArgumentParser()
    parser.add_argument("serial", type=str)
    parser.add_argument("host", type=str)
    args=parser.parse_args()

    with SshTunnel(args.host) as tun:
        db = _mysql.connect(user='metaRO', host='127.0.0.1', port=tun.mysql_port, db='meta', passwd='test321')
        db.query("""
            SELECT uuid FROM merchant WHERE id = (SELECT merchant_id FROM device_provision WHERE serial_number = '{}');
             """.format(args.serial))
        row = db.store_result().fetch_row(how=0)
        print(row[0][0].decode('utf-8'))
    return
