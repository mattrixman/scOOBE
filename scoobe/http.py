import requests
import json
import pprint as pp
from copy import deepcopy
from enum import Enum
from scoobe.common import StatusPrinter, Indent, shorten, pretty_shorten, is_identity

class Verb(Enum):
    get = requests.get
    post = requests.post
    put = requests.put
    patch = requests.patch
    delete = requests.delete

def print_request(printer, endpoint, headers, data):
    printer("[Request] " + endpoint)
    with Indent(printer):
        printer("headers:")
        with Indent(printer):
            printer(pp.pformat(headers, indent=2))
        printer("data:")
        with Indent(printer):
            printer(pretty_shorten(data))

def pretty_shorten_maybe_json(response):

    content_str = str(response.content)
    if response.encoding:
        content_str = response.content.decode(response.encoding)

    try:
        content_dict = json.loads(content_str)
    except ValueError:
        return pretty_shorten(content_str)

    if 'elements' in content_dict:
        return pretty_shorten(content_dict['elements'])
    else:
        return pretty_shorten(content_dict)

def print_response(printer, response):
    printer("[Response]")
    with Indent(printer):
        printer("code:", end='')
        printer(response.status_code)
        printer("reason:", end='')
        printer(response.reason)
        printer("content:")
        with Indent(printer):
            printer(pretty_shorten_maybe_json(response))

def _do_request(verb, endpoint, headers, data, print_data=None, printer=StatusPrinter()):

    # for obfuscating passwords
    if not print_data:
        print_data = data

    printer("[Http]")
    with Indent(printer):
        print_request(printer, endpoint, headers, print_data)
        if data:
            if 'json' in ''.join(headers.values()).lower():
                response = verb(endpoint, headers=headers, json=data)
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
