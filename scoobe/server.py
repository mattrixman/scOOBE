import sh
from time import sleep
import sys
import _mysql
import socket
from sh import cat, sed, awk, tail, ErrorReturnCode_1
from os.path import expanduser, join, exists

def mysql_port(host):
    try:
        ssh_config = join(expanduser('~'),'.ssh','config')
        port = int(str(awk(tail(sed(cat(ssh_config), '-n', '/Host ' + host + '$/,/3306/p'), '-n', 1), '{print $2}')).strip())
        assert(port > 0)
        assert(port < 65536)
    except Exception as ex:
        print("Do you have your ~/.ssh/config set up to forward a local port to 3306 on {}?".format(host) +
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


def go():
    with SshTunnel('dev1') as dev1:
        db = _mysql.connect(user='root', host='127.0.0.1', port=dev1.mysql_port, db='meta', passwd='test123')
        db.query("""
                 SELECT @@hostname;
                 """)
        result = db.store_result()
        return result.fetch_row(how=1)
