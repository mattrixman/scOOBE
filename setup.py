from setuptools import setup
setup(name='scoobe',
      version='0.1.0.dev1',
      description='commands for manipulating a device through oobe',
      url='https://github.com/mattrixman/scoobe',
      author='Matt Rixman',
      author_email='matt.rixman@clover.com',
      packages=['scoobe'],
      python_requires= '>=3',
      install_requires=['uiautomator', 'sh'],
      entry_points={'console_scripts' : ['press_button = scoobe.button:press',
                                         'device_info = scoobe.device:info',
                                         'wait_ready = scoobe.device:wait_ready'] }
      )

