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


- adb should work, like so:

     ❯ adb devices
         List of devices attached
         C030UQ72330608  device

- ssh should authenticate without prompting for a password, like so:

      ❯ ssh dev1
          ... output omitted...
          [<your user>@dev1.dev ~]$

- While the above ssh session is active, there should be a local port which is forwarded to the mysql port on the target machine.

Fore more about how to configure this, see: [this confluence page](https://confluence.dev.clover.com/pages/viewpage.action?pageId=20711161)

### The First Time

    # get python3 and (recommended) venv
    ❯ apt update && apt install -y git python3-venv

    # get the repo
    ❯  git clone https://github.com/mattrixman/scOOBE && cd scOOBE

    # create a virtual environment (this makes a folder)
    ❯ python3 -m venv .venv

    # enter it (by sourcing the script in the newly created folder)
    .venv ❯ source .venv/bin/activate

    # get the latest version of the package manager
    .venv ❯ pip installl --upgrade pip

    # add scoobe snacs to the virtual environment (also download dependencies)
    .venv ❯ python setup.py develop

    # plug in your device and do stuff with scoobe snacs
    .venv ❯ device_info
        {"marketing_name": "Mini", "code_name": "MAPLECUTTER", "serial": "C030UQ72330608", "targeting": "local:10.249.253.118", "cpuid": "00000001740e21801000000007018640"}

    # exit the venv
    .venv ❯ deactivate

    # note that the scoobe snacs aren't avaliable
    ❯ device_info
        command not found: device_info

### Subsequent Times:

    # activate the venv
    ❯ source .venv/bin/activate

    # do stuff
    .venv ❯ device_info | jq .targeting
        "local:10.249.253.118"

    # exit the venv
    .venv ❯ deactivate

## Example Session

##### Set the device target to dev1

    .venv ❯ target_device dev dev1.dev.clover.com && wait_ready && device_info | jq .targeting
        targeting device to: dev1.dev.clover.com
        waiting for device  ... ready
        "dev:dev1.dev.clover.com"

##### See which merchant is associated with this device

    .venv ❯ device_merchant $(device_serial) dev1
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

    .venv ❯ provision_device $(device_serial) $(device_cpuid) dev1 TCF09QDYHEDQ8
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

    .venv ❯ device_merchant $(device_serial) dev1
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

## Supported Devices

Unit tests pass for Flex and Mini, other devices coming soon.

## scoobe snacs

See [setup.py](setup.py) for a list of commands.  Each supports interactive help, like so:

    .venv ❯ provision_device -h
        usage: provision_device [-h] serial_num cpuid ssh_config_host merchant

        positional arguments:
          serial_num       the device serial number
          cpuid            the device cpu id
          ssh_config_host  ssh alias, appears: 'Host: <here>' in ~/.ssh/config
          merchant         UUID of merchant that will be using this device

## With an IDE

To use scoobe snacs from an IDE, enter the virtual environment and launce your IDE from there:

    ❯ source .venv/bin/activate
    .venv ❯ idea /path/to/project

From there, you can invoke a snac like you would any other command.

![screenshot of IDE session](ide.png)

Notice that the status messages are written to STERR, but the requested data is written to STDOUT.  This makes it easy to get what you asked for, while still knowing what went down--which is probably important since it's your user thats doing these things.

## Feedback

Feel free to submit bugs and feature requests as issues.  PR's happily accepted too.

