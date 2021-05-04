import unittest
from simple_cdd import env
import tempfile
import os

class TestEnv(unittest.TestCase):
    def setUp(self):
        # Save and clear the environment before the tests
        self.saved_env = dict(os.environ)
        os.environ.clear()

    def tearDown(self):
        # Restore the environment after the tests
        os.environ.clear()
        for k, v in self.saved_env.items():
            os.environ[k] = v

    def test_knownvar_text(self):
        VARIABLES = [
            env.TextVar("test", "default")
        ]

        # If the variable does not exist in the environment, it gets the
        # default value
        e = env.Environment(VARIABLES)
        self.assertEqual(e.test, "default")

        # If the variable does exists in the environment, the environment value
        # is used
        os.environ["test"] = "somevalue"
        e = env.Environment(VARIABLES)
        self.assertEqual(e.test, "somevalue")

    def test_unknownvar(self):
        # Unknown values raise AttributeError via the getattr interface, even
        # if set in the environment, but are still accessible via get()
        e = env.Environment([])
        with self.assertRaises(AttributeError):
            e.test
        self.assertEqual(e.get("test"), "")

        os.environ["test"] = "somevalue"
        e = env.Environment([])
        with self.assertRaises(AttributeError):
            e.test
        self.assertEqual(e.get("test"), "somevalue")

    def test_expansion(self):
        # Case of expansion that broke in the past
        VARIABLES = [
            env.PathVar("simple_cdd_dir", "test",
                    help="simple-cdd working directory"),
            env.PathVar("simple_cdd_temp", ["{simple_cdd_dir}", "tmp"],
                    help="directory where intermediate build data are stored"),
            env.PathVar("simple_cdd_mirror", ["{simple_cdd_temp}", "mirror"],
                    help="directory where the local mirror is stored"),
            env.PathVar("MIRROR", "{simple_cdd_mirror}",
                    help="directory where the local mirror is stored"),
        ]
        e = env.Environment(VARIABLES)
        self.assertEqual(e.MIRROR, "test/tmp/mirror")

        VARIABLES = [
            env.BoolVar("a", True),
            env.BoolVar("b", "{a}"),
        ]
        e = env.Environment(VARIABLES)
        self.assertEqual(e.a, True)

    def test_configfile(self):
        VARIABLES = [
            env.BoolVar("use_security_mirror", help="merge Debian security updates into mirror"),
        ]
        e = env.Environment(VARIABLES)
        self.assertFalse(e.use_security_mirror)
        e.set("use_security_mirror", True)
        self.assertTrue(e.use_security_mirror)

        with tempfile.NamedTemporaryFile(mode="wt") as fd:
            print("use_security_mirror=false", file=fd)
            fd.flush()
            e.read_config_file(fd.name)
        self.assertFalse(e.use_security_mirror)

