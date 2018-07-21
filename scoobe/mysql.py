import MySQLdb
import MySQLdb.cursors
import pprint as pp
from enum import Enum
from textwrap import dedent
from scoobe.common import StatusPrinter, Indent, shorten, pretty_shorten, is_identity
from scoobe.properties import LocalServer
from scoobe.ssh import SshConfig, PossibleSshTunnel

# encapsulates the feedback you might expect from a mysql query
class Feedback(Enum):

    # rowtransform is a function that takes a row (as a dict of {'row_name' : 'row_value'}) and makes it into
    # whatever shape the user wants it in.

    def OneRow(cursor, rowtransform, print_transform=False, printer=StatusPrinter()):

        row = cursor.fetchone()

        next_row = cursor.fetchone()
        if next_row:
            raise Exception("OneRow feedback strategy saw at least two rows: {} and {}".format(row, next_row))
            # this function refuses to break ties for you
            # if you expected multiple rows, use the ManyRows feedback strategy and break them yourself


        # exit early if response is empty
        if not row:
            printer("...got empty result")
            return None

        printer('[Row]')
        with Indent(printer):
            printer(shorten(row))

        # exit early if transform is trivial
        if is_identity(rowtransform):
            return row

        row = rowtransform(row)

        if print_transform:
            printer('[Transformed Row]')
            with Indent(printer):
                printer(pretty_shorten(row))

        return row

    def ManyRows(cursor, rowtransform, print_transform=False, printer=StatusPrinter()):

        # exit early if response is empty
        rows = cursor.fetchall()
        if not rows:
            printer("...got empty result")
            return None

        printer('[Rows]')
        with Indent(printer):
            printer(shorten(rows))

        # exit early if transform is trivial
        if is_identity(rowtransform):
            return rows


        rows = list(map(rowtransform, rows))

        if print_transform:
            printer('[Transformed Rows]')
            with Indent(printer):
                printer(pretty_shorten(rows))

        return rows

    def ChangeCount(cursor, rowtransform, print_transform=False, printer=StatusPrinter()):

        if not is_identity(rowtransform):
            printer("ChangeCount got nontrivial row transform.  It will be ignored.")

        change_ct = cursor.rowcount

        printer('[Rows Changed]')
        with Indent(printer):
            printer(change_ct)

        return change_ct


# encapsulates a mysql query
class Query:
    def __init__(self, ssh_config, mysql_user, mysql_pass, sql):
        self.ssh_config = ssh_config
        self.mysql_user = mysql_user
        self.mysql_pass = mysql_pass
        self.sql = sql

    # If host='localhost' then mysql tries to use the socket (local fs) and doesn't actually connect through the tunnel
    # This forces everything through the network socket (slower, but consistent between ssh-tunneled and
    # locally-running usage)
    def get_mysql_host(configured_host):
        if configured_host != 'localhost':
            return configured_host
        else:
            return '127.0.0.1'

    # called externally when the user doesn't need to read data
    # called internally, parameter will be called with post-query connection string
    def execute(self, feedback, rowtransform=lambda x : x, print_transform=False, printer=StatusPrinter()):
        # open an ssh tunnel
        with PossibleSshTunnel(self.ssh_config, printer) as tun:
            with Indent(printer):

                host = Query.get_mysql_host(tun.mysql().host)

                # open a mysql connection
                db = MySQLdb.connect(user=self.mysql_user,
                                    host=host,
                                    port=tun.mysql().port,
                                    db=tun.mysql().db,
                                    passwd=self.mysql_pass,
                                    autocommit=True,
                                    cursorclass=MySQLdb.cursors.DictCursor)
                c = db.cursor()

                # show the query then run it
                printer("[Query]")
                with Indent(printer):
                    printer(dedent(self.sql).strip())
                c.execute(self.sql)

                # do what the caller wanted
                return feedback(c, rowtransform, print_transform=print_transform, printer=printer)
