#! /usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ORIG="$(pwd)"
set -uo pipefail

cd "$DIR"

if python --version | grep '3\.' > /dev/null ; then
    python -m unittest -v
else
    echo "Please use python 3"
    echo "(consider setting up a virtual environment:"
    echo "    python3 -m venv .venv       # <-- create it "
    echo "    source .venv/bin/activate   # <-- enter it "
    echo "    python setup.py develop     # <-- set it up for this project"
    echo "    $0"
    echo "    deactivate                  # <-- to exit it"
    echo ")"
    echo "(or using an existing one:"
    echo "    source .venv/bin/activate"
    echo "    $0"
    echo "    deactivate"
    echo ")"
fi

cd "$ORIG"

# to run just one test class:
# python -m unittest test.test_device.Device
# python -m unittest test.test_device.Device.test_adb_available
