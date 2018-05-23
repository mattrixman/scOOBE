import unittest
import _mysql
from scoobe import server
import sys

class Server(unittest.TestCase):

    def setUp(self):
        # this will throw if your ssh config isn't set up right
        # see: https://confluence.dev.clover.com/pages/viewpage.action?pageId=20711161
        config = server.SshConfig('dev1')

    def test_throw_if_no_host(self):
        try:
            # back up stdout
            stdout = sys.stdout

            # nullify stdout
            sys.stdout = server.SshTunnel.NullDevice()

            # make some noise
            with self.assertRaises(ValueError):
                config = server.SshConfig('asdfasdfasdf')

        finally:
            # restore stdout
            sys.stdout = stdout

    def test_dont_reopen_tunnel(self):
        config = server.SshConfig('dev1')
        with server.SshTunnel(config) as tun:
            with self.assertRaises(Exception):
                with server.SshTunnel(config) as tun2:
                    self.assertFail(msg="SshTunnel should throw before control makes it here")


#    def test_throw_if_host_but_no_forward(self):
#        with self.assertRaises(ValueError):
#            server.mysql_port('github.com')


    # This test pases
    def test_query_through_tunnel(self):
        config = server.SshConfig('dev1')
        with server.SshTunnel(config) as tun:
            db = _mysql.connect(user='root', host='127.0.0.1', port=tun.mysql_port, db='meta', passwd='test123')
            db.query("""
                     SELECT @@hostname;
                     """)
            row = db.store_result().fetch_row(how=1)
        self.assertTrue('dev1' in row[0]['@@hostname'].decode('utf-8'))
