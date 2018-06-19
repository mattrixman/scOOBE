import sys
import re
import socket
from time import sleep
from sh import ssh
from sh import ErrorReturnCode
from collections import namedtuple
from sshconf import read_ssh_config
from os.path import expanduser, join
from scoobe.common import StatusPrinter, Indent, ServerTarget, UserPass

# returns true if the specified port is open on the local machine
def port_open(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1',port))
    sock.close()
    return result == 0


# encapsulates the local ssh config entry for a particular host
# makes some assumptions about the remote configuration (default passwords, etc)
class SshConfig(ServerTarget):

    def __init__(self, host, printer=StatusPrinter):
        try:
            # Read the local ssh config
            configs = read_ssh_config(join(expanduser('~'),'.ssh','config'))
            if host not in configs.hosts():
                raise ValueError("{} not configured in ~/.ssh/config".format(host))
            config = configs.host(host)

            # initialize fields on the object with entries in the ssh config
            config['hostname'] # throw if not set
            self.__dict__.update(config)

            # also find the local ports which are is forwarded to the remote mysql daemon and the admin interface (http)
            ports = SshConfig._get_ports(config, printer)
            self._mysql_port = ports.mysql
            self._admin_http_port = ports.admin

            # ssh tunnel not used for external-facing access, assume port 80
            self._http_port = 80

            # and include the config section name
            self._ssh_host = host

        except Exception as ex:
            printer(ex)
            printer("Do you have your ~/.ssh/config set up to forward a local port to 3306 on {}? ".format(host) +
                    "If not, see https://confluence.dev.clover.com/pages/viewpage.action?pageId=20711161")
            raise ex

    # given an ssh config entry, parse forwarded ports
    def _get_ports(config_section, printer):

        # we will return one of these
        Ports = namedtuple('Ports', 'mysql admin')

        # ensure a config section exists
        try:
            forwards = config_section['localforward']
        except KeyError:
            raise ValueError("{} has no port forwarding in ~/.ssh/config".format(config_entry))

        # A way to parse strings like this:
        # <local_port>    <host>:<remote_port>
        # 10002        127.0.0.1:3306
        def read_ports(forward_str):
            # return these
            Forward = namedtuple('Forward', 'local_port remote_port')

            m = re.match(r'(\d*) .*:(\d+).*', forward_str)
            if m:
                return Forward(int(m.group(1)), int(m.group(2)))
            else:
                return None

        # parse them all
        forwards = [x for x in map(read_ports, config_section['localforward']) if x is not None]

        # find the mysql port
        mysql =  next(filter(lambda x: x.remote_port == 3306, forwards), None)

        if mysql:
            printer("Locally forwarded mysql port: {}".format(mysql))
        else:
            raise ValueError("Could not find local mysql port in {}".format(forwards))

        # assume the other one is the http admin port
        non_mysql_ports = filter(lambda x: x.remote_port != 3306, forwards)

        admin = next(non_mysql_ports, None)

        # warn if there were three or more
        if len(list(non_mysql_ports)) > 1:
            printer("Found multiple non-mysql port forwards: {}".format(config_section.localforward))

        if admin:
            printer("Assuming {} is the http admin port".format(admin))
        else:
            # Http admin access is optional, remain quiet about its absence
            pass

        # what do ports look like?
        def validate(port):
            assert(port > 0)
            assert(port < 65536)

        # do these look like ports?
        validate(mysql.local_port)
        if admin is not None:
            validate(admin.local_port)

        return Ports(mysql.local_port, admin.local_port)

    def verify_admin_port(self):
        if not hasattr(self._admin_http_port):
            raise ValueError("~/.ssh/config entry: {} has no port forwarded to the http admin interface.".format(
                self.get_name()))

    def get_name(self):
        return self._ssh_host

    def get_hostname(self):
        return self.hostname

    def get_http_port(self):
        return 80

    def get_mysql_port(self):
        return self._mysql_port

    def get_db_name(self):
        return 'meta'

    def get_admin_hostname(self):
        self.verify_admin_port()
        return 'localhost'

    def get_admin_http_port(self):
        self.verify_admin_port()
        return self._admin_http_port

    def get_readonly_mysql_creds(self):
        return UserPass('metaRO', 'test321')

    # read-write
    def get_readwrite_mysql_creds(self):
        return UserPass('metaRO', 'test789')

# encapsulates an ssh session, which holds the tunnel open
# unless the target is local, in which case this is a meaningless wrapper
Http = namedtuple('HostPort', 'host port')
Mysql = namedtuple('HostPort', 'host port db ro rw')
class PossibleSshTunnel:

    def __init__(self, target, printer=StatusPrinter()):
        # target is either a properties file (local) or an ssh config (remote)
        assert(isinstance(target, ServerTarget))

        self.print = printer
        self.target = target

        self._connect = False
        if isinstance(target, SshConfig):
            self._connect = True

            if port_open(self.target.get_mysql_port()):
                raise OSError("The local port ({}) you're trying to forward is already open.  "
                                  .format(self.target.get_mysql_port())
                             + "Close it first.")

            # begin connecting
            self._process = ssh(self.target.get_name(), _bg=True)


    # These calls let the caller be agnostic about whether the ssh tunnel is in use or not
    def mysql(self):
        return Mysql('localhost',
                self.target.get_mysql_port(),
                self.target.get_db_name(),
                self.target.get_readonly_mysql_creds(),
                self.target.get_readwrite_mysql_creds())

    def external_http(self):
        return HostPort(self.target.get_hostname(), 80)

    def admin_http(self):
        return HostPort('localhost', self.target.get_admin_http_port())

    def get_readonly_mysql_creds(self):
        return UserPass('metaRO', 'test321')

    def get_readwrite_mysql_creds(self):
        return UserPass('metaRW', 'test789')

    # For hiding useless output from the ssn connection, impersonates stdout
    class NullDevice:
        def write(self, s):
            pass

    # set up the connection, if necessary
    def __enter__(self):

        if self._connect:
            self.print('[Connecting to ' + self.target.get_name(), end='')
            # wait for connection to come up
            connected = False
            while not connected:
                self.print('.', end='')
                connected = port_open(self.target.get_mysql_port())
                sleep(1)
            self.print(']')
        else:
            self.print('[Target is local, not connecting]')
        return self

    # close the connection, if necessary
    def __exit__(self, type, value, traceback):

        if self._connect:
            # silence THIS SYSTEM IS RESTRICTED... by pointing sys.stderr to a null device
            # keep a backup so we can write to it in the interm and restore it later
            orig_stderr = sys.stderr
            status_print = StatusPrinter(file=orig_stderr)
            try:
                sys.stderr = PossibleSshTunnel.NullDevice()
                self._process.terminate()
            except ErrorReturnCode:
                pass

            # wait for connection to drop
            connected = True
            self.print('[Disconnecting from ' + self.target.get_name(), end='')
            while connected:
                self.print('.', end='')
                connected = port_open(self.target.get_mysql_port())
                sleep(1)
            self.print(']')
            sys.stderr = orig_stderr
        else:
            self.print('[Target is local, nothing to disconnect]')
