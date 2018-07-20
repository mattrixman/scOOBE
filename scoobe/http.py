import requests
import json
from copy import deepcopy
from enum import Enum
from scoobe.common import StatusPrinter, Indent

class Verb(Enum):
    get = requests.get
    post = requests.post
    put = requests.put
    patch = requests.patch
    delete = requests.delete

def print_request(printer, endpoint, headers, data):
    printer("[Request] " + endpoint)
    with Indent(printer):
        printer("headers:", end='')
        with Indent(printer):
            printer(headers)
        printer("data:", end='')
        with Indent(printer):
            printer(data)

def print_response(printer, response):
    printer("[Response]")
    with Indent(printer):
        printer("code:", end='')
        printer(response.status_code)
        printer("reason:", end='')
        printer(response.reason)
        printer("content:", end='')
        if isinstance(response.content, str):
            printer(response.content)
        else:
            if (response.encoding):
                printer(response.content.decode(response.encoding))
            else:
                printer(response.content)

def _do_request(verb, endpoint, headers, data, is_json=False, print_data=None, printer=StatusPrinter()):

    # for obfuscating passwords
    if not print_data:
        print_data = data

    printer("[Http]")
    with Indent(printer):
        print_request(printer, endpoint, headers, print_data)
        if data:
            if 'json' in ''.join(headers.values()).lower():
                response = verb(endpoint, headers=headers, data=json.dumps(data))
            else:
                response = verb(endpoint, headers=headers, data=data)
        else:
            response = verb(endpoint, headers=headers)
        print_response(printer, response)
    return response

def get(endpoint, headers, printer=StatusPrinter):
    return _do_request(Verb.get, endpoint, headers, None, printer=printer)

def put(endpoint, headers, data, printer=StatusPrinter()):
    return _do_request(Verb.put, endpoint, headers, data, printer=printer)

def post(endpoint, headers, data, obfuscate_pass=False, printer=StatusPrinter()):
    if obfuscate_pass:
        safe_data = deepcopy(data)
        safe_data['password'] = '*' * len(data['password'])
        return _do_request(Verb.post, endpoint, headers, data, print_data=safe_data, printer=printer)
    else:
        return _do_request(Verb.post, endpoint, headers, data, printer=printer)
