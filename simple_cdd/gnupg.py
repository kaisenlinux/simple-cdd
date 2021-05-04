from simple_cdd.exceptions import Fail
from simple_cdd.utils import run_command
import os
import subprocess
import logging

log = logging.getLogger()


class Gnupg:
    """
    Collect all gnupg related functions
    """

    def __init__(self, env):
        self.env = env

    def init_homedir(self):
        gnupghome = self.env.get("GNUPGHOME")
        if not os.path.isdir(gnupghome):
            os.makedirs(gnupghome, exist_ok=True)
            os.chmod(gnupghome, 0o700)

        # Import all keyrings into our gnupg home
        for keyring_file in self.env.get("keyring"):
            if not os.path.exists(keyring_file):
                log.warn("keyring file %s does not exist", keyring_file)
                continue
            self.import_keyring(keyring_file)


    def common_gpg_args(self):
        args = ["gpg", "--batch", "--no-default-keyring"]
        for k in self.env.get("keyring"):
            args.extend(("--keyring", k))
        return args

    def extract_inline_contents(self, pathname, sigpathname):
        args = self.common_gpg_args() + ["--decrypt", sigpathname]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        if stdout and proc.returncode == 0:
            lines = stdout.splitlines(keepends=True)
            with open(pathname, 'w') as x:
                for line in lines:
                    x.write(line.decode('utf-8'))
        else:
            raise Fail("Unable to extract data from %s to %s, returned %d", sigpathname, pathname, proc.returncode)

    def verify_gpg_sig(self, *extra_args):
        args = self.common_gpg_args()
        args.extend(extra_args)
        retval = run_command("verify gpg signature", args)
        if retval != 0:
            raise Fail("Signature verification failed on %s", args)

    def verify_detached_sig(self, pathname, sigpathname):
        return self.verify_gpg_sig("--verify", sigpathname, pathname)

    def verify_inline_sig(self, pathname):
        return self.verify_gpg_sig("--verify", pathname)

    def import_keyring(self, keyring_file):
        """
        Import a keyring into our keyring file
        """
        env = dict(os.environ)
        env["GNUPGHOME"] = self.env.get("GNUPGHOME")
        proc = subprocess.Popen(["gpg", "--batch", "--import", keyring_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        stdout, stderr = proc.communicate()
        retval = proc.wait()
        if retval != 0:
            for line in stderr.decode("utf-8").split("\n"):
                log.error("GPG standard error: %s", line)
            raise Fail("Importing %s into %s failed, gpg error code %s", keyring_file, self.env.get("GNUPGHOME"), retval)

    def list_valid_keys(self, keyring_file):
        """
        Generate a sequence of keyIDs for valid signing keys found in the given
        keyring file
        """
        keys_raw = subprocess.check_output(["gpg",
                                            "--batch",
                                            "--no-default-keyring",
                                            "--keyring", keyring_file,
                                            "--list-keys",
                                            "--with-colons"],
                                            universal_newlines=True)
        for line in keys_raw.split("\n"):
            if not line.startswith("pub") and not line.startswith("sub"):
                continue
            fields = line.split(":")
            keyid = fields[4]
            status = fields[11]
            if 'D' in status: continue
            if 's' not in status and 'S' not in status: continue
            # Append '!' to keyid to allow expired keys in the
            # keyring, though reprepro still requires
            # --ignore=expired* arguments in order to treat signatures
            # from expired keys as valid.
            # https://bugs.debian.org/928703
            yield keyid+'!'
