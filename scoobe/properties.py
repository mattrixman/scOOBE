import argparse
import re
import os
from collections import namedtuple
from scoobe.common import ServerTarget, UserPass

# is this a valid file?
def valid_file(s):
    if not os.path.exists(s):
        msg = "File does not exist: " + s
        raise argparse.ArgumentTypeError(msg)
    else:
        return s

class LocalServer(ServerTarget):

    # is this a valid server properties file? If so, return an object containing the relevant ones
    def __init__(self, s):
        valid_file(s)

        name2mask = { 'port'       : 'port=(.*)',
                      'admin_port' : 'adminPort=(.*)',
                      'db_name'     : 'metaDbName=(.*)',
                      'ro_user'     : 'metaDbUsersRO=([^,]*)',
                      'ro_pass'     : 'metaDbPasswordsRO=([^,]*)',
                      'rw_user'     : 'metaDbUser=(.*)',
                      'rw_pass'     : 'metaDbPassword=(.*)' }

        with open(s) as prop_file:
            props = prop_file.read()

            for (name, mask) in name2mask.items():
                match = re.search(mask, props)
                if match:
                    setattr(self, '_' + name, match.group(1))
                else:
                    raise argparse.ArgumentTypeError("Invalid props file: " + s)

        self._file = str(s)
        print("__init__: ", s)
        self._name = "the local server with `-profile {0}`".format(self._file)

    def get_name(self):
        return self._name

    def get_db_name(self):
        return self._db_name

    def get_hostname(self):
        return "localhost"

    def get_http_port(self):
        return self._port

    def get_hypertext_protocol(self):
        return 'http'

    def get_mysql_port(self):
        return 3306

    def get_admin_hostname(self):
        return 'localhost'

    def get_admin_http_port(self):
        return self._admin__port

    def get_readonly_mysql_creds(self):
        return UserPass(self._ro_user, self._ro_pass)

    def get_readwrite_mysql_creds(self):
        return UserPass(self._rw_user, self._rw_pass)
