from simple_cdd.exceptions import Fail
from simple_cdd.utils import run_command, shell_quote
import os.path
import logging

log = logging.getLogger()


class Tool:
    """
    Base class for external tools
    """
    TOOLS = {}

    @classmethod
    def register(cls, tool):
        """
        Decorator used to register a Tool object so that it can be found when
        tools need to be run
        """
        cls.TOOLS[(tool.type, tool.name)] = tool
        return tool

    @classmethod
    def create(cls, env, type, name):
        """
        Create a tool runner for this type and name.
        """
        tool = cls.TOOLS.get((type, name), None)
        if tool is None:
            return ToolShell(env, type, name)
        else:
            return tool(env)


class ToolShell(Tool):
    """
    Base class for tools implemented as shell scripts
    """
    # Tool type (build, mirror, testing)
    type = "unknown"
    # Tool name
    name = "unknown"

    def __init__(self, env, type=None, name=None):
        """
        Basic initialization, and lookup of the full pathname of the shell
        script.

        ToolShell can be used directly without subclassing, to run shell tools
        without extra checks or exports.
        """
        if type is not None: self.type = type
        if name is not None: self.name = name
        self.env = env
        self.pathname = self.find_script()

    def find_script(self):
        """
        Find the full pathname of the script to be run
        """
        for d in self.env.get("simple_cdd_dirs"):
            pathname = os.path.join(d, "tools", self.type, self.name)
            if not os.path.exists(pathname): continue
            return pathname
        raise Fail("Cannot find tool %s/%s in %s", self.type, self.name, self.env.get("simple_cdd_dirs"))

    def check_pre(self):
        """
        Run checks before running the script
        """
        pass

    def check_post(self, retval):
        """
        Run checks after running the script
        """
        pass

    def _make_run_script(self):
        """
        Make a script that can be used to run this tool in the current
        environment
        """
        logdir = self.env.get("simple_cdd_logs")
        scriptname = os.path.join(logdir, "{}-{}".format(self.type, self.name))

        # Write out what we are doing into a script, both as clear
        # documentation and as a way to rerun this step by hand and tweak
        # it for debugging
        with open(scriptname, "wt") as fd:
            print("#!/bin/sh", file=fd)
            print("# Execute tool {}/{}".format(self.type, self.name), file=fd)
            print("", file=fd)
            print("# Export environment", file=fd)
            for name, val, changed in self.env.export_iter():
                if val.help: print("#", val.help, file=fd)
                print("export {}={}".format(name, shell_quote(str(val))), file=fd)
            print("", file=fd)
            print("# Run the tool", file=fd)
            print("exec /bin/sh -ue {} \"$@\"".format(shell_quote(self.pathname)), file=fd)
        os.chmod(scriptname, 0o755)

        return scriptname

    def run_script(self):
        """
        Just build and run the script, without pre and post checks.

        This is useful so that run() can be overridden to do more setup and
        teardown that just the checks, and running the script can still be
        delegated to this method
        """
        # Check if the environment has changed since last run
        log.info("Running tool %s", self.pathname)
        scriptname = self._make_run_script()
        retval = None
        logfilename = scriptname + ".log"
        with open(logfilename, "wt") as fd:
            retval = run_command(
                        "{}/{}".format(self.type, self.name),
                        [scriptname],
                        env={},
                        logfd=fd)

            if retval == 0:
                log.info("%s/%s ran successfully, full log can be found in %s", self.type, self.name, scriptname)
            else:
                raise Fail("%s/%s exited with code %s, full log can be found in %s", self.type, self.name, retval, scriptname)
        return retval

    def run(self):
        """
        Export variables and run the script
        """
        self.check_pre()
        retval = self.run_script()
        self.check_post(retval)



