import unittest
import _mysql
from scoobe import server

class Server(unittest.TestCase):

    def setUp(self):
        # this will throw if your ssh config isn't set up right
        # see: https://confluence.dev.clover.com/pages/viewpage.action?pageId=20711161
        server.mysql_port('dev1')

    # This test pases
    def test_query_through_tunnel(self):
        with server.SshTunnel('dev1') as tun:
            db = _mysql.connect(user='root', host='127.0.0.1', port=tun.mysql_port, db='meta', passwd='test123')
            db.query("""
                     SELECT @@hostname;
                     """)
            row = db.store_result().fetch_row(how=1)
        self.assertTrue('dev1' in row[0]['@@hostname'].decode('utf-8'))

