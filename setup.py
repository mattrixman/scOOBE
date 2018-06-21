from setuptools import setup
setup(name='scoobe',
      version='0.1.0.dev1',
      description='commands for manipulating a device through oobe',
      url='https://github.com/mattrixman/scoobe',
      author='Matt Rixman',
      author_email='matt.rixman@clover.com',
      packages=['scoobe'],
      python_requires= '>=3',
      install_requires=['uiautomator', 'sh', 'mysqlclient', 'sshconf', 'requests', 'ifaddr', 'sortedcontainers'],
      entry_points={'console_scripts' : [
          # press the button with the given text
          'press_button = scoobe.ui:press',

          # wait for the given text to appear on the screen
          'wait_text = scoobe.ui:wait_text',

          # reset device, clear storage
          'master_clear = scoobe.device:master_clear',

          # print a json dictionary of stuff about the device
          'device_info = scoobe.device:print_info',

          # if the device is rebooting, wait for it to be ready for further commands
          'wait_ready = scoobe.device:wait_ready',

          # given a device serial number, point it at a server (whose details are specified in ~/.ssh/config)
          'target_device = scoobe.device:set_target',

          # print the device's serial number
          'device_serial = scoobe.device:print_serial',

          # print the device's cpu id
          'device_cpuid = scoobe.device:print_cpuid',

          # find an IP address pair, each of which can ping each other, one goes with a network interface on the device
          # the other that goes with localhost
          'probe_network = scoobe.device:probe_network',

          # probe the network (like above) but only print the local ip
          'device_facing_local_ip = scoobe.device:print_local_ip',

          # probe the network (like above) but only print the device ip
          'device_ip = scoobe.device:print_device_ip',

          # given a serial number and a server, see which merchant the server thinks the device goes with
          'device_merchant = scoobe.server:print_merchant',

          # given a merchant uuid, print the merchant id that goes with it
          'get_merchant_id = scoobe.server:print_merchant_id',

          # given a serial number and a server, see which reseller the server thinks the device goes with
          'device_reseller = scoobe.server:print_device_reseller',

          # given a serial number, a server, and a reseller id, set this device to that reseller according to that server
          'set_device_reseller = scoobe.server:print_set_device_reseller',

          # given a merchant_id and a server, see which reseller the server thinks the merchant goes with
          'merchant_reseller = scoobe.server:print_merchant_reseller',

          # detach the specified device from whichever merchant it is currently associated with
          'deprovision_device = scoobe.server:deprovision',

          # attach the specified device to the specified merchant (modifies device reseller if necessary)
          'provision_device = scoobe.server:provision',

          # clear the ACCEPTED_BILLING_TERMS flag
          'unaccept_terms= scoobe.server:unaccept',

          # set the ACCEPTED_BILLING_TERMS flag
          'accept_terms= scoobe.server:accept',

          # get the activation code for a device (won't work if not provisioned)
          'activation_code = scoobe.server:print_activation_code',

          # set the activation code for a device (becomes stale on first use)
          'set_activation_code = scoobe.server:print_set_activation',

          # refresh the activation code for a device if it is stale
          'refresh_activation = scoobe.server:print_refresh_activation',

          ]})
