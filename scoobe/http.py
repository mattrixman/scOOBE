import requests
import json
import pprint as pp
import os
import sys
from copy import deepcopy
from enum import Enum
from scoobe.common import StatusPrinter, Indent, shorten, pretty_shorten, is_identity
from scoobe.ssh import SshConfig, UserPass

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

# Server Specific:

def get_creds(printer=StatusPrinter()):

    user_exists = False
    user_var='LDAP_USER'
    if user_var in os.environ:
        user = os.environ[user_var]
        user_exists = True
    # else: warn later so we can warn for both

    passwd_exists=False
    passwd_var='LDAP_PASSWORD'
    if passwd_var in os.environ:
        passwd = os.environ[passwd_var]
        passwd_exists = True
    # else: warn later so we can warn for both

    try:
        return UserPass(user, passwd)
    except NameError:
        with Indent(printer):
            printer("Please set environment variables:")
            with Indent(printer):

                if not user_exists:
                    printer(user_var)
                    with Indent(printer):
                        printer("(try typing: 'export {}=<your_username>' and rerunning the command)".format(
                            user_var))

                if not passwd_exists:
                    printer(passwd_var)
                    with Indent(printer):
                        printer("(try typing: \'read -s {} && export {}\', ".format(passwd_var, passwd_var),
                                "typing your password, and rerunning the command)")
                if not (user_exists and passwd_exists):
                    sys.exit(100)


def internal_auth(target,
                  creds = {'username' : 'joe.blow',
                           'password' : 'letmein' },
                  printer=StatusPrinter()):

    endpoint = '{}://{}/cos/v1/dashboard/internal/login'.format(
                target.get_hypertext_protocol(),
                target.get_hostname() + ":" + str(target.get_http_port()))

    headers = { 'Content-Type' : 'application/json ',
                      'Accept' : 'application/json, text/javascript, */*; q=0.01',
                  'Connection' : 'keep-alive' }

    data = creds

    # first try with with a nonsense user
    printer("Attempting cloverDevAuth")
    with Indent(printer):
        response = post(endpoint, headers, data, obfuscate_pass=True, printer=printer)

    if response.status_code == 200:
        return response.headers['set-cookie']

    # if that fails, use a real one
    elif response.status_code == 401:
        printer("{} has cloverDevAuth unset or false, looking for real credentials".format(target.get_name()))

        creds = get_creds(printer=printer)
        data = {'username' : creds.user,
                'password' : creds.passwd}

        with Indent(printer):
            response = post(endpoint, headers, data, obfuscate_pass=True, printer=printer)

            if response.status_code == 200:
                return response.headers['set-cookie']
            else:
                raise Exception("Unexpected response from login endpoint")

def make_uri(path, target):

    return'{}://{}:{}/{}'.format(
        target.get_hypertext_protocol(),
        target.get_hostname(),
        target.get_http_port(),
        path)

def _headers(target, printer=StatusPrinter()):

    return { 'Content-Type' : 'application/json ',
                   'Accept' : 'application/json, text/javascript, */*; q=0.01',
               'Connection' : 'keep-alive',
                   'Cookie' : internal_auth(target, printer=printer) }

def _finish(response, verb_str, uri, descend_once, printer=StatusPrinter()):

    if response.status_code < 200 or response.status_code > 299:
        raise Exception("{} on {} returned code {}".format(verb_str, uri, response.status_code))

    if descend_once:
        return json.loads(response.content.decode('utf-8'))[descend_once]
    return json.loads(response.content.decode('utf-8'))

def get_response_as_dict(path, target, descend_once='elements', printer=StatusPrinter()):

    uri = make_uri(path, target)
    headers = _headers(target, printer=printer)
    response = get(uri, headers, printer=printer)

    return _finish(response, 'GET', uri, descend_once)

def put_response_as_dict(path, target, data, descend_once=None, printer=StatusPrinter()):

    uri = make_uri(path, target)
    headers = _headers(target, printer=printer)
    response = put(uri, headers, data, printer=printer)
    return _finish(response, 'PUT', uri, descend_once)

def post_response_as_dict(path, target, data, descend_once=None, printer=StatusPrinter()):

    uri = make_uri(path, target)
    headers = _headers(target, printer=printer)
    response = post(uri, headers, data, printer=printer)

    return _finish(response, 'POST', uri, descend_once)
