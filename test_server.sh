#! /usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ORIG="$(pwd)"
set -uo pipefail

cd "$DIR"

if python --version | grep '3\.' > /dev/null ; then
    python -m unittest -v test.test_server.Server
else
    echo "Please use python 3"
    echo "(consider using a virtual environment:"
    echo "    python3 -m venv .venv && source .venv/bin/activate"
    echo "    $0"
    echo "    deactivate # <-- to exit the evironment"
    echo ")"
fi

cd "$ORIG"
