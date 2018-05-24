import sys
import re
import socket
from time import sleep
from sh import ssh
from sh import ErrorReturnCode
from collections import namedtuple
from sshconf import read_ssh_config
from os.path import expanduser, join
from scoobe.common import StatusPrinter, Indent

# returns true if the specified port is open on the local machine
def port_open(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1',port))
    sock.close()
    return result == 0


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

    def __init__(self, config, printer=StatusPrinter()):
        self.print = printer

        # not a true hostname, this is the alias ssh config uses for each config entry
        self.host = config.ssh_host

        self.mysql_port = config.mysql_port

        if port_open(self.mysql_port):
            raise OSError("The local port ({}) you're trying to forward is already open.  ".format(self.mysql_port) +
                            "Close it first.")

        self.process = ssh(self.host, _bg=True)

    def __enter__(self):
        connected = False

        # wait for connection to come up
        self.print('[Connecting to ' + self.host, end='')
        while not connected:
            self.print('.', end='')
            connected = port_open(self.mysql_port)
            sleep(1)
        self.print(']')
        return self

    def __exit__(self, type, value, traceback):

        # silence THIS SYSTEM IS RESTRICTED... by pointing sys.stderr to a null device
        # keep a backup so we can write to it in the interm and restore it later
        orig_stderr = sys.stderr
        status_print = StatusPrinter(file=orig_stderr)
        try:
            sys.stderr = SshTunnel.NullDevice()
            self.process.terminate()
        except ErrorReturnCode:
            pass

        # wait for connection to drop
        connected = True
        self.print('[Disconnecting from ' + self.host, end='')
        while connected:
            self.print('.', end='')
            connected = port_open(self.mysql_port)
            sleep(1)
        self.print(']')
        sys.stderr = orig_stderr
