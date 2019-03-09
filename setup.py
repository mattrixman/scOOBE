from setuptools import setup
setup(name='scoobe',
      version='0.2.0.dev1',
      description='commands for manipulating a device through oobe',
      url='https://github.com/mattrixman/scoobe',
      author='Matt Rixman',
      author_email='matt.rixman@clover.com',
      packages=['scoobe'],
      python_requires= '>=3',
      install_requires=['uiautomator', 'sh', 'mysqlclient', 'sshconf', 'requests', 'ifaddr', 'sortedcontainers', 'xmltodict'],
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

          # point the connected device at a server
          'target_device = scoobe.device:set_target',

          # print the device's serial number
          'device_serial = scoobe.device:print_serial',

          # print the device's cpu id
          'device_cpuid = scoobe.device:print_cpuid',

          # dump the device screen to png
          'screenshot = scoobe.device:print_screenshot',

          # find an IP address pair that can ping the other.
          # One goes with a network interface on the device,
          # the other that goes with a network interface on localhost.
          'probe_network = scoobe.device:probe_network',

          # probe the network (like above) but only print the local ip
          'device_facing_local_ip = scoobe.device:print_local_ip',

          # probe the network (like above) but only print the device ip
          'device_ip = scoobe.device:print_device_ip',

          # given a serial number and a server, see which merchant the server thinks the device goes with
          'device_merchant = scoobe.server:print_device_merchant',

          # given a serial number and a server, see which merchant the server thinks the device goes with
          'register_device = scoobe.server:print_register_device',

          # given a merchant uuid or a merchant id, print the other
          'merchant = scoobe.server:print_merchant',

          # given a serial number and a server, see which reseller the server thinks the device goes with
          'device_reseller = scoobe.server:print_device_reseller',

          # print the version names for all packages on the device matching 'com.clover*'
          'device_packages = scoobe.device:print_device_packages',

          # given a serial number, a server, and a reseller id, set this device to that reseller according to that server
          'set_device_reseller = scoobe.server:print_set_device_reseller',

          # given a merchant_id and a server, see which reseller the server thinks the merchant goes with
          'merchant_reseller = scoobe.server:print_merchant_reseller',

          # detach the specified device from whichever merchant it is currently associated with
          'deprovision_device = scoobe.server:deprovision',

          # attach the specified device to the specified merchant (modifies device reseller if necessary)
          'provision_device = scoobe.server:provision',

          # see whether this merchant has accepted billing terms
          'terms_accepted= scoobe.server:print_acceptedness',

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

          # create a new merchant
          'new_merchant = scoobe.server:print_new_merchant',

          # get a session cookie (asks the user to initialize some environment varibles if they are not set)
          'internal_login = scoobe.server:print_cookie',

          # describe the resellers on this server
          'resellers = scoobe.server:print_resellers',

          # assign a reseller to a merchant
          'set_merchant_reseller = scoobe.server:print_set_merchant_reseller',

          # list the merchant plan groups on this server
          'plan_groups = scoobe.server:print_plan_groups',

          # given a plan_group uuid or a merchant id, print the other
          'plan_group = scoobe.server:print_plan_group',

          # create a new plan group
          'new_plan_group = scoobe.server:print_new_plan_group',

          # dump an existing plan to json
          'get_plan = scoobe.server:print_get_plan',

          # read a new plan from json
          'new_plan = scoobe.server:print_new_plan',

          # update an existing plan from json
          'set_plan = scoobe.server:print_set_plan',

          # list the partner controls on this server
          'partner_controls = scoobe.server:print_partner_controls',

          # dump an existing partner_control to json
          'get_partner_control = scoobe.server:print_get_partner_control',

          # read a new partner_control from json
          'new_partner_control = scoobe.server:print_new_partner_control',

          # update an existing partner_control from json
          'set_partner_control = scoobe.server:print_set_partner_control',

          # which plan does this partner control board to?
          'get_partner_control_plan = scoobe.server:print_get_partner_control_plan',

          # change the plan that this partner control boards to
          'set_partner_control_plan = scoobe.server:print_set_partner_control_plan',

          # dump an existing reseller to json
          'get_reseller = scoobe.server:print_get_reseller',

          # read a new reseller from json
          'new_reseller = scoobe.server:print_new_reseller',

          # update an existing reseller from json
          'set_reseller = scoobe.server:print_set_reseller',

          # list the merchant's installed apps
          'merchant_apps = scoobe.server:print_get_merchant_apps',

          # list the available apps
          'apps = scoobe.server:print_get_apps',

          # list the configured event subscriptions
          'event_subscriptions = scoobe.server:print_get_event_subscriptions',

          # show details for the configured event subscription
          'event_subscription = scoobe.server:print_get_event_subscription',

          # create a new event subscription
          'new_event_subscription = scoobe.server:print_new_event_subscription',

          # pick a merchant at random
          'random_merchant = scoobe.server:print_random_merchant',

          # what are your permissions on this server?
          'my_permissions = scoobe.server:print_my_permissions',

          # what are the available permissions on this server?
          'permissions = scoobe.server:print_permissions',

          # grant yourself the indicated permission on this server
          'set_permission = scoobe.server:print_set_permission',

          ]})
