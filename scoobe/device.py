from sh import adb
from sh import head
from sh import grep
import re

def info():
    d = Device()
    print({"type" : d.type,
           "serial" : d.serial,
           "cpuid" : d.cpuid })

class Device:

    # use digits 2-4 to identify device
                    #C?XX
    prefix2device = { "10" : "GOLDLEAF",
                      "20" : "LEAFCUTTER",
                      "21" : "LEAFCUTTER",
                      "30" : "MAPLECUTTER",
                      "31" : "MAPLECUTTER",
                      "32" : "KNOTTY_PINE",
                      "41" : "BAYLEAF",
                      "42" : "BAYLEAF",
                      "50" : "GOLDEN_OAK" }

    def __init__(self):

        # adb shell getprop | grep serial | head -n 1
        self.serial = str(head(grep(adb.shell('getprop'), 'serial') ,'-n', '1'))[-17:-3]

        # adb shell getprop | grep cpuid | head -n 1
        self.cpuid = str(head(grep(adb.shell('getprop'), 'cpuid') ,'-n', '1'))[-35:-3]

        # https://confluence.dev.clover.com/display/ENG/How+to+decipher+a+Clover+device+serial+number
        self.type = Device.prefix2device[self.serial[2:4]]

