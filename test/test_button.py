import unittest
import scOOBE.Button as Button

class Bar(unittest.TestCase):

    # This test pases
    def test_foo(self):
        b = Button('todo','todo')
        self.assertEqual('foo', b.test())

    def test_bar(self):
        self.assertEqual('bar', Button.test2())
