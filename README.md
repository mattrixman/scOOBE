# Scripted Control of OOBE

This is a collection of small scripts.  Each completes a small OOBE-related task.  The idea is that these would be called by a more comprehensive test automation solution.

## To use

- clone the repo
- cd to the toplevel dir
- `python setup.py develop`
- start using scOOBE commands

## Supported Devices

Unit tests pass for Flex and Mini, other devices coming soon.

## scOOBE commands

Here is an example session:

    ❯ set_target dev dev1.dev.clover.com && wait_ready
    targeting device to: dev1.dev.clover.com
    waiting for device  ... ready

    ❯ device_info
    {'serial': 'C041UQ73770227', 'targeting': 'dev:https://dev1.dev.clover.com', 'code_name': 'BAYLEAF', 'marketing_name': 'Flex', 'cpuid': '0000000B00000000E6669C184341B72E'}

    ❯ set_target local 10.249.253.118
    targeting device to: 10.249.253.118

