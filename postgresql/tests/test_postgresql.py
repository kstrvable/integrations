import unittest

from outlyer_plugin import OutlyerPluginTest

class TestPlugin(unittest.TestCase):

    def test_postgresqlplugin(self):
        variables = {}
        output = OutlyerPluginTest.run_plugin("../plugins/postgresql.py", variables)
        output.print_output()

if __name__ == '__main__':
    unittest.main()
