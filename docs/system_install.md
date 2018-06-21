# System Install

scoobe snacs consists of [several commands](../setup.py) which--once installed, will be available at the command line.
You may want to conser a [venv install](venv_install.md) if:
    - You'd prefer to control when the scOOBE suite of commands id available
    - You expect to be making changes to scOOBE itself

If you don't mind scOOBE being installed system-wide, then you're in the right place

## To install

    # get the repo and enter its root
    ❯  git clone https://github.com/mattrixman/scOOBE && cd scOOBE

    # invoke the installer
    ❯ python3 setup.py install

## To use

    # plug in your device and do stuff with scoobe snacs
    ❯ device_info
        {"marketing_name": "Mini", "code_name": "MAPLECUTTER", "serial": "C030UQ72330608", "targeting": "local:10.249.253.118", "cpuid": "00000001740e21801000000007018640"}

