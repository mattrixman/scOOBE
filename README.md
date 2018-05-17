# SCOOBE SNACS

*S*cripted
*C*ontrol of the
*O*ut
*O*f
*B*ox
*E*xperience

*S*ometimes
*N*eeds
*A*dditional
*C*ontrol
*S*emantics

This is a collection of commands.  Each completes a small OOBE-related task.  The idea is that these would be called by a more comprehensive test automation solution.

## To use

### The First Time

    # get python3 and (optionally) venv
    ❯ apt update && apt install -y git python3-venv

    # get the repo
    ❯  git clone https://github.com/mattrixman/scOOBE && cd scOOBE

    # create a virtual environment (this makes a folder)
    ❯ python3 -m venv .venv

    # enter it (by sourcing the script in the newly created folder)
    .venv ❯ source .venv/bin/activate

    # get the latest version of the package manager
    .venv ❯ pip installl --upgrade pip

    # add the scOOBE commands to your environment
    .venv ❯ python setup.py develop

    # do stuff
    .venv ❯ device_info
        {"marketing_name": "Mini", "code_name": "MAPLECUTTER", "serial": "C030UQ72330608", "targeting": "local:10.249.253.118", "cpuid": "00000001740e21801000000007018640"}

    # exit the venv
    .venv ❯ deactivate

    ❯ device_info
        command not found: device_info

### Subsequent Times:

    # activate the venv
    ❯ source .venv/bin/activate

    # do stuff
    .venv ❯ device_info | jq .targeting
        "local:10.249.253.118"

    .venv ❯ set_target dev dev1.dev.clover.com && wait_ready && device_info | jq .targeting
        targeting device to: dev1.dev.clover.com
        waiting for device  ... ready
        "dev:dev1.dev.clover.com"

    # exit the venv
    .venv ❯ deactivate

## Supported Devices

Unit tests pass for Flex and Mini, other devices coming soon.

## scOOBE commands

|command|behavior|
|:--|:--|
|device_info| print the serial number, cpuid, cloud target url, and model info as a JSON string |
|set_target target url| retarget the device (causes a reboot) |
|wait_ready | block until the device finishes rebooting |
