import subprocess
import sys
import os
import re
import json
import tempfile
try:
    # After Python 3.3
    from collections.abc import Iterable
except ImportError:
    # This has changed in Python 3.3 (why, oh why?), reinforcing the idea that
    # the best Python version ever is still 2.7, simply because upstream has
    # promised that they won't touch it (and break it) for at least 5 more
    # years.
    from collections import Iterable
from .utils import shell_quote
import logging

log = logging.getLogger()


class Backtick:
    """
    Represent a value obtained by executing a command and reading its standard
    output. This allows to use commands as default values for configuration
    variables.
    """
    def __init__(self, *command):
        self.val = command
        self.cached_result = None

    def __str__(self):
        return "$({})".format(" ".join(shell_quote(x) for x in self.val))

    def __call__(self):
        if self.cached_result is None:
            self.cached_result = subprocess.check_output(self.val, universal_newlines=True).strip()
        return self.cached_result


class Variable:
    """
    Base class for environment variable proxies.

    This acts as a glue between the configuration files, the environment,
    python, the command line arguments and the scripts that we run.
    """
    def __init__(self, name, default=None, cmdline=None, help=None, env=None):
        # Name of the variable in the environment
        self.name = name
        # Default value of the variable, as a python value that will be read or
        # evaluated when the variable value is requested and none has been set
        self.default = default
        # Name(s) of command line arguments to set this variable
        if isinstance(cmdline, str):
            self.cmdline = [cmdline]
        else:
            self.cmdline = cmdline
        # Documentation for this variable
        self.help = help
        # Current environment (usually set later)
        self.env = env
        # Current value, stored as a string ready to be exported in the
        # environment
        self.current = None
        # Set to true when the variable was automatically created and not
        # defined in the code
        self.automatically_created = False

    def __str__(self):
        """
        Get the current value as a string
        """
        if self.current is None:
            # TODO: build a value from the defaults
            res = self.default_to_string()
        else:
            res = self.current
        return res

    def to_parser(self, parser):
        """
        Add an option for this variable to the command line parser
        """
        default = self.format_default()
        if default == "":
            parser.add_argument(*self.cmdline, action="store", dest=self.name, help=self.help)
        else:
            help = self.help + " (default: {})".format(default)
            parser.add_argument(*self.cmdline, action="store", dest=self.name, help=help)

    def format_default(self):
        """
        Format the default value for showing in documentation and command line
        help
        """
        return str(self.default)

    def default_to_string(self):
        """
        Convert the default value to a string
        """
        if callable(self.default):
            # If 'default' is a python callable, call it and return its result
            return str(self.default())
        elif self.default is None:
            return ""
        elif isinstance(self.default, str):
            return self.env.format(self.default)
        else:
            return str(self.default)

    def to_python(self):
        """
        Return the current value as a python value
        """
        # To be overridden
        return str(self)

    def from_python(self, value):
        """
        Set the current value from a python value
        """
        # To be overridden
        self.current = str(value)

    def from_commandline(self, value):
        """
        Set the current value from a command line option
        """
        if value is None:
            return
        elif value is True:
            self.current = "true"
        elif value is False:
            self.current = ""
        else:
            self.current = value.strip()


class BoolVar(Variable):
    """
    A proxy for a boolean environment variable. For python it behaves as a
    bool, and for the environment it will be "true" for True and "" for False
    """
    def to_parser(self, parser):
        default = self.format_default()
        help = self.help + " (default: {})".format(default)
        parser.add_argument(*self.cmdline, action="store_true", dest=self.name, help=help)

    def format_default(self):
        if isinstance(self.default, bool):
            return "true" if self.default else "false"
        else:
            return super().format_default()

    def default_to_string(self):
        if isinstance(self.default, bool):
            bval = self.default
        else:
            bval = super().default_to_string() == "true"
        return "true" if bval else ""

    def to_python(self):
        return str(self) == "true"

    def from_python(self, value):
        self.current = "true" if value else ""


class TextVar(Variable):
    """
    A proxy for a string environment variable. For python it behaves as a
    str, and for the environment it will be a string.
    """
    pass


class PathVar(Variable):
    """
    A proxy for a string environment variable that contains a path. For python
    it behaves as a str, and for the environment it will be a string. It
    supports appending, and default variables in the form of a string, which
    will be properly concatenated into a path.
    """
    def append(self, value):
        if not isinstance(value, str):
            raise ValueError("Attempted to append a non-string value to a path")
        self.from_python(os.path.join(str(self), value))

    def format_default(self):
        if isinstance(self.default, str):
            return self.default
        elif isinstance(self.default, Iterable):
            return os.path.join(self.default)
        else:
            return super().format_default()

    def default_to_string(self):
        if isinstance(self.default, str):
            return self.env.format(self.default)
        elif isinstance(self.default, Iterable):
            formatted = [self.env.format(x) for x in self.default]
            return os.path.join(*formatted)
        else:
            return super().default_to_string()

class ListVar(Variable):
    """
    A proxy for a string environment variable that contains a list of strings.
    For python it behaves as a sequence, and for the environment it will be a
    space separated string. It supports appending. Command line arguments can
    be space or comma separated.
    """
    def append(self, value):
        cur = self.to_python()
        if isinstance(value, str):
            cur.append(value)
        elif isinstance(value, Iterable):
            cur.extend(value)
        else:
            raise ValueError("Attempted to append a {} value to a list".format(value.__class__))
        self.from_python(cur)

    def format_default(self):
        if isinstance(self.default, str):
            return self.default
        elif isinstance(self.default, Iterable):
            return " ".join(self.default)
        else:
            return super().format_default()

    def default_to_string(self):
        if isinstance(self.default, str):
            return self.env.format(self.default)
        elif isinstance(self.default, Iterable):
            return " ".join(self.env.format(x) for x in self.default)
        else:
            return super().default_to_string()

    def to_python(self):
        val = str(self)
        if val:
            return val.split()
        else:
            return []

    def from_python(self, value):
        if value:
            if isinstance(value, str):
                self.current = value
            elif isinstance(value, Iterable):
                self.current = " ".join(value)
            else:
                raise ValueError("Attempted to append a {} value to a path".format(value.__class__))
        else:
            self.current = ""

    def from_commandline(self, value):
        if isinstance(value, str):
            items = re.split(r"\s*,\s*", value.strip())
            self.current = " ".join(items)
        else:
            super().from_commandline(value)

class Environment:
    """
    Keep track of environment changes
    """
    def __init__(self, variables):
        env = {}
        for v in variables:
            v.env = self
            if v.name in env:
                raise AssertionError("{} defined twice".format(v.name))
            env[v.name] = v
            if v.name in os.environ:
                v.current = os.environ[v.name]
        for name, val in os.environ.items():
            if name in env: continue
            v = TextVar(name, help="Preexisting environment variable {}".format(name))
            env[name] = v
            v.automatically_created = True
            v.current = val
        super().__setattr__("env", env)
        super().__setattr__("initial", dict(os.environ))

    def parse_commandline(self, args):
        """
        Set values from command line arguments
        """
        for name, v in self.env.items():
            if v.cmdline is None: continue
            v.from_commandline(getattr(args, name))

    def get(self, name):
        """
        Get a value by name, returns the empty string if not found
        """
        val = self.env.get(name, None)
        if val is None:
            return ""
        else:
            return val.to_python()

    def set(self, name, value):
        """
        Set a value by name, converting the python value to the type of the variable name.
        """
        cur = self.env.get(name, None)
        if cur is None:
            self.env[name] = cur = TextVar(name, env=self)
            cur.automatically_created = True
        cur.from_python(value)

    def set_from_commandline(self, name, value):
        """
        Set a value by name, converting the user string value to the type of the variable name.
        """
        cur = self.env.get(name, None)
        if cur is None:
            self.env[name] = cur = TextVar(name, env=self)
            cur.automatically_created = True
        cur.from_commandline(value)

    def append(self, name, value):
        """
        Append elements or sequences to a list
        """
        cur = self.env.get(name, None)
        if cur is None:
            self.env[name] = cur = TextVar(name, env=self)
        cur.append(value)

    def unset(self, name):
        """
        Unset an element
        """
        del self.env[name]

    def read_config_file(self, pathname):
        """
        Source a config file and edit configuration from its environment
        """
        log.info("Reading configuration file %s", pathname)
        # Write the source wrapper to a temporary file and execute it
        with tempfile.NamedTemporaryFile("w+t") as fd:
            print("set -a", file=fd)
            print(". " + os.path.abspath(pathname), file=fd)
            print("exec {} -c 'import os,json,sys;json.dump(dict(os.environ),sys.stdout)'".format(sys.executable), file=fd)
            fd.flush()
            out = subprocess.check_output(["sh", fd.name]).decode("utf-8")
        # Parse its output
        if not out.strip(): return
        lines = out.split("\n")
        # Pass through stdout from the script
        for line in lines[:-1]:
            print(line)
        # Parse the environment set by the script
        new_env = json.loads(lines[-1])
        # Diff our environment and the script one, to see what was set
        for key in new_env.keys() - os.environ.keys():
            log.info("%s: new var %s=%s", pathname, key, shell_quote(new_env[key]))
            self.set_from_commandline(key, new_env[key])
        for key in new_env.keys() & os.environ.keys():
            if os.environ[key] == new_env[key]: continue
            log.info("%s: changed var %s=%s", pathname, key, shell_quote(new_env[key]))
            self.set_from_commandline(key, new_env[key])

    def export_iter(self):
        """
        Generate a sequence of (name, value, changed) where:
            name is the variable name
            value is the variable value as a string
            changed is a boolean that is True if the value has changed since
                    the original environmenf at program startup
        """
        for name, val in sorted(self.env.items()):
            valstr = str(val)
            yield name, val, valstr != self.initial.get(name, None)

    def export(self):
        """
        Export variables for the script
        """
        os.environ.clear()
        for name, val, changed in self.export_iter():
            if changed:
                log.info("export %s=%s", name, shell_quote(val))
            #else:
            #    log.info("export %s=%s", name, shell_quote(val))
            os.environ[name] = val

    def format(self, string, *args, **kw):
        """
        Call string.format() including all the known env vars
        """
        kwargs = dict(self.env)
        kwargs.update(**kw)
        return string.format(*args, **kwargs)

    def __getattr__(self, name):
        """
        Get a value by name, raises exception if not found
        """
        val = self.env.get(name, None)
        if val is None or val.automatically_created:
            raise AttributeError("Environment has no variable '{}'".format(name))
        else:
            return val.to_python()

    def __setattr__(self, name, val):
        """
        Get a value by name, raises exception if not found
        """
        val = self.env.get(name, None)
        if val is None:
            super().__setattr__(name, val)
        else:
            cur.from_python(value)
