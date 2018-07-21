import sys
import pprint as pp
from textwrap import indent
from enum import Enum
from abc import ABC, abstractmethod
from collections import namedtuple

# don't log huge responses
max_line = 200
max_rows = 20

# trim str(data) by length only
def shorten(data):
    string = str(data)
    if len(string) <= max_line:
        return string
    else:
        return string[0:max_line] + '...'

# trim pretty-printed data (frequently multi-line) by line length and num-lines
def pretty_shorten(data):

    output = ''

    if type(data) != str:
        pretty_string = pp.pformat(data, indent=2)
    else:
        pretty_string = data

    for idx, line in enumerate(pretty_string.split('\n')):
        output+=shorten(line) + '\n'
        if idx > max_rows:
            output+='...'
            break

    return output

# nontrivial transforms get extra output
# this tests to see if the user-supplied transform is trivial
def is_identity(func):
    try:
        test_dict = {'foo' : 'bar'}
        if func(test_dict) == test_dict:
            return True
        else:
            return False
    except:
        return False


UserPass = namedtuple('UserPass', 'user passwd')

class ServerTarget(ABC):

    def __init__(self):
        super().__init__()

    # a user-defined name for this host
    # - might be a hostname
    # - might be an ssh config entry
    @abstractmethod
    def get_name(self):
        pass

    # the hostname to use for public-facing network access
    @abstractmethod
    def get_hostname(self):
        pass

    # the port to use for public-facing network access
    @abstractmethod
    def get_http_port(self):
        pass

    # "http" or "https"
    @abstractmethod
    def get_hypertext_protocol(self):
        pass

    @abstractmethod
    def get_mysql_port(self):
        pass

    @abstractmethod
    def get_db_name(self):
        pass

    # the hostname to use for http admin access
    # and also mysql access
    @abstractmethod
    def get_admin_hostname(self):
        pass

    # the port to use for http admin access
    @abstractmethod
    def get_admin_http_port(self):
        pass

    # read-only
    @abstractmethod
    def get_readonly_mysql_creds(self):
        pass

    # read-write
    @abstractmethod
    def get_readwrite_mysql_creds(self):
        pass


# print status to stderr so that only the requested value is written to stdout
# (the better for consumption by a caller)
# default to a four-space indent
class StatusPrinter:
    def __init__(self, indent=4, file=sys.stderr):
        self.indent = indent
        self.at_line_begin = True
        self.file = file

    def __call__(self, msg, end='\n'):

        if self.at_line_begin:
            this_indent = self.indent
        else:
            this_indent =  0

        if end is '':
            self.at_line_begin = False
        else:
            self.at_line_begin = True

        print(indent(msg.__str__(), ' ' * this_indent), file=self.file, end=end)

# Increments the intent depth for a StatusPrinter
class Indent:
    def __init__(self, printer):
        self.printer = printer

    def __enter__(self):
        self.printer.indent += 4

    def __exit__(self, type, value, traceback):
        self.printer.indent -= 4
