# SCOOBE SNACS

**S**cripted

**C**ontrol of the

**O**ut

**O**f

**B**ox

**E**xperience

.

**S**ometimes

**N**eeds

**A**dditional

**C**ontrol

**S**emantics

This is a collection of commands.  Each completes a small OOBE-related task.  The idea is that these would be useful both when called by a more comprehensive test automation solution (i.e. intellij) and also when typed by a human into a (bash or python) shell.  It is useful in its present state, but it is not complete.

## To use

### Prerequisites

##### python 3.3 or greater should be installed

To check:

    python3 --version

To install:

    brew install python3

##### mysql_config is available

To check:

    which mysql_config

To install:

    brew install mysql


##### adb should work

Like so:

    ❯ adb devices
        List of devices attached
        C030UQ72330608  device

##### ssh authenticates via keys (no password prompt)

Like so:

    ❯ ssh dev1
        ... output omitted, no input needed ...
    [<your user>@dev1.dev ~]$

Fore more about how to configure this, see: [this confluence page](https://confluence.dev.clover.com/pages/viewpage.action?pageId=20711161)

##### Port Forwarding

While the above ssh session is active, there should be a local port which is forwarded to the mysql port on the target machine, this is covered in the above article as well.

If you're running server locally, instead of the ssh config name, provide the path to the properties file.  Details of the locally-running server will be read from the file, and the forward-a-port step will be skipped.

### Installation

See either:

- [system install](docs/system_install.md) (recommended if you don't plan to modify scOOBE)
- [venv install](docs/venv_install.md) (recommended if you do)

## Example Session

##### Set the device target to dev1

    ❯ target_device dev dev1.dev.clover.com

##### See which merchant is associated with this device

    ❯ device_merchant $(device_serial) dev1
        Finding C030UQ72330608's merchant according to dev1
            [Connecting to dev1...]
                [Query]
                    SELECT id, uuid
                    FROM merchant
                    WHERE id = (SELECT merchant_id
                                FROM device_provision
                                WHERE serial_number = 'C030UQ72330608');
                ...got empty result
            [Disconnecting from dev1.]
        this device is not associated with a merchant on dev1

##### Set the merchant for this device

    ❯ provision_device $(device_serial) $(device_cpuid) dev1 TCF09QDYHEDQ8
        Provisioning Device
            [Connecting to dev1...]
                [Query]
                    SELECT HEX(at.uuid)
                    FROM authtoken at
                    JOIN authtoken_uri atu
                        ON at.id = atu.authtoken_id
                    WHERE
                            atu.uri = '/v3/partner/pp/merchants/{mId}/devices/{serialNumber}/provision'
                        AND
                            at.deleted_time IS NULL LIMIT 1;
                [Result]
                    {'HEX(at.uuid)': b'6386THIS_IS_AN_AUTHENTICATION_TOKEN4567'}
            [Disconnecting from dev1.]
            [Connecting to dev1...]
                [Query]
                    SELECT id FROM merchant WHERE uuid='TCF09QDYHEDQ8' LIMIT 1;
                [Result]
                    {'id': '3085'}
            [Disconnecting from dev1.]
            [Http Request] https://dev1.dev.clover.com/v3/partner/pp/merchants/TCF09QDYHEDQ8/devices/C030UQ72330608/provision
                headers:{'Authorization': 'Bearer 6386THIS_IS_AN_AUTHENTICATION_TOKEN4567'}
                data:{'merchantUuid': 'TCF09QDYHEDQ8', 'mId': 3085, 'chipUid': '00000001740e21801000000007018640', 'serial': 'C030UQ72330608'}
            [Http Response]
                code:200
                reason:OK
                content:{"activationCode":"22885693"}
        OK

    ❯ device_merchant $(device_serial) dev1
        Finding C030UQ72330608's merchant according to dev1
            [Connecting to dev1...]
                [Query]
                    SELECT id, uuid
                    FROM merchant
                    WHERE id = (SELECT merchant_id
                                FROM device_provision
                                WHERE serial_number = 'C030UQ72330608');
                [Result]
                    {'id': '3085', 'uuid': b'TCF09QDYHEDQ8'}
            [Disconnecting from dev1.]
        {"id": "3085", "uuid": "TCF09QDYHEDQ8"}

##### Wait for a reboot to complete and press "Pick Language"

    ❯ wait_ready && press_button "Pick Language"
        waiting for device  ... ready

##### Wait for a connection and press "Next"

    ❯ wait_text "Successfully connected" && press_button "Next"
        waiting for text ... found

##### More coming soon...

## Supported Devices

Unit tests pass for Flex and Mini, other devices coming soon.

## SNAC List

See [setup.py](setup.py) for the full list.  Each supports interactive help, like so:

    ❯ provision_device -h
        usage: provision_device [-h] serial_num cpuid ssh_config_host merchant

        positional arguments:
          serial_num       the device serial number
          cpuid            the device cpu id
          ssh_config_host  ssh host of the server (specified in ~/.ssh/config)
          merchant         UUID of merchant that will be using this device

## With an IDE

You can invoke a snac like you would any other command.

![screenshot of IDE session](docs/ide.png)

Notice that the status messages are written to STERR, but the requested data is written to STDOUT.  This makes it easy to get what you asked for, while still knowing what happened.

## Versions

| Version | Focus |
| :-- | :-- |
| [v0.0](https://github.com/mattrixman/scOOBE/releases/tag/v0.0) | Initial Release |
| [v0.1](https://github.com/mattrixman/scOOBE/releases/tag/v0.1) | Local Server, Reseller Support, System 2018 |

## Feedback

Feel free to submit bugs and feature requests as issues.  PR's happily accepted too.

