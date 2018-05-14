#! /usr/bin/python3

import unittest
import os.path
import glob
from pathlib import Path 

# scan `./test` for files matching `test_*`
test_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test')
test_expr = os.path.join(test_dir, 'test_*')
test_files = glob.glob(test_expr)


# import all such files
import importlib
for test_file in test_files:
    importlib.import_module("test.{}".format(Path(test_file).stem))

# run all tests
def run_all():
    loader = unittest.TestLoader()
    suite = loader.discover(test_dir)
    runner = unittest.TextTestRunner()
    runner.run(suite)


if __name__ == "__main__":
    run_all()
