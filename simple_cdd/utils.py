from .exceptions import Fail
from debian import deb822
import subprocess
import fcntl
import select
import shlex
import re
import hashlib
import os
import logging
import shutil
import sys

log = logging.getLogger()

if hasattr(shlex, "quote"):
    shell_quote = shlex.quote
else:
    import pipes
    shell_quote = pipes.quote

if hasattr(shutil, "which"):
    shell_which = shutil.which
else:
    # Available since python 1.6:
    # http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
    from distutils.spawn import find_executable
    shell_which = find_executable

def stream_output(proc):
    """
    Take a subprocess.Popen object and generate its output, line by line,
    annotated with "stdout" or "stderr". At process termination it generates
    one last element: ("result", return_code) with the return code of the
    process.
    """
    fds = [proc.stdout, proc.stderr]
    bufs = [b"", b""]
    types = ["stdout", "stderr"]
    # Set both pipes as non-blocking
    for fd in fds:
        fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)
    # Multiplex stdout and stderr with different prefixes
    while len(fds) > 0:
        s = select.select(fds, (), ())
        for fd in s[0]:
            idx = fds.index(fd)
            buf = fd.read()
            if len(buf) == 0:
                fds.pop(idx)
                if len(bufs[idx]) != 0:
                    yield types[idx], bufs.pop(idx)
                types.pop(idx)
            else:
                bufs[idx] += buf
                lines = bufs[idx].split(b"\n")
                bufs[idx] = lines.pop()
                for l in lines:
                    yield types[idx], l
    res = proc.wait()
    yield "result", res


def run_command(name, cmd, env=None, logfd=None):
    """
    Run a command logging its output.

    name is the name used to identify the command in logs

    cmd is the command itself

    env is the environment to run the command in. If missing, the current
    environment is used.

    logfd, if present, is a file where the full output of the command will also
    be written.
    """
    quoted_cmd = " ".join(shell_quote(x) for x in cmd)
    log.debug("%s running command %s", name, quoted_cmd)
    if logfd: print("runcmd:", quoted_cmd, file=logfd)

    # Run the script itself on an empty environment, so that what was
    # documented is exactly what was run
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    stderr = []
    for type, val in stream_output(proc):
        if type == "stdout":
            val = val.decode("utf-8").rstrip()
            if logfd: print("stdout:", val, file=logfd)
            log.debug("%s stdout: %s", name, val)
        elif type == "stderr":
            val = val.decode("utf-8").rstrip()
            if logfd: print("stderr:", val, file=logfd)
            if val: stderr.append(val)
            log.debug("%s stderr: %s", name, val)
        elif type == "result":
            if logfd: print("retval:", val, file=logfd)
            log.debug("%s retval: %d", name, val)
            retval = val

    if retval != 0:
        lastlines = min(len(stderr), 5)
        log.error("%s exited with code %s", name, retval)
        log.error("Last %d lines of standard error:", lastlines)
        for line in stderr[-lastlines:]:
            log.error("%s: %s", name, line)

    return retval


def verify_preseed_file(pathname):
    """
    Verify that a preseed file is valid.

    Returns true if it is valid, false otherwise.
    """
    # # verify that preseeding files are valid
    proc = subprocess.Popen(["/usr/bin/debconf-set-selections", "--checkonly", pathname],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    res = None
    re_ignore_stderr = re.compile(r'debconf: DbDriver "passwords" warning: could not open /var/cache/debconf/passwords.dat: Permission denied')
    for type, val in stream_output(proc):
        if type == "stdout":
            pass
        elif type == "stderr":
            val = val.decode("utf-8")
            if not re_ignore_stderr.match(val):
                print(val, file=sys.stderr)
        elif type == "result":
            res = val

    return res == 0


def list_debs(file_or_dir):
    """
    Generated all .deb or .udeb files recursively found inside the given
    directories.

    If an argument is a file, and is a .deb or .udeb, it is also generated
    """
    wanted = re.compile(r".*\.(deb|udeb)$")
    if os.path.isfile(file_or_dir):
        if wanted.search(file_or_dir):
            yield file_or_dir
    elif os.path.isdir(file_or_dir):
        for root, dirs, files in os.walk(file_or_dir):
            for f in files:
                if not wanted.search(f): continue
                yield os.path.join(root, f)
    else:
        log.warning("local package source %s is neither a file nor a directory", file_or_dir)


class Checksums:
    """
    In-memory database of file checksums
    """
    FIELDS = ["MD5Sum", "SHA1", "SHA256"]

    def __init__(self, env):
        # dict mapping pathnames to { size: int, MD5Sum: str, SHA1: str, SHA256: str }
        #
        # Only those checksum fields actually present in the Release file will
        # exist. size is also optional.
        self.by_relname = {}
        # Files that have been parsed to collect checksums
        self.sources = []
        # Parameters
        self.env = env

    def verify_file(self, absname, relname):
        """
        Verify if a file matches the checksums. Fails if it does not, or if we
        do not have a checksum for it.
        """
        # Get the checksum record for this file
        file_sums = self.by_relname.get(relname, None)
        if file_sums is None:
            if self.env.get("ignore_missing_checksums"):
                log.warning("Ignoring missing checksum for %s", relname)
                return
            else:
                raise Fail("No checksums found for %s in %s", relname, ", ".join(self.sources))

        # Check file size if we have it
        expected_size = file_sums.get("size", None)
        if expected_size is not None:
            real_size = os.stat(absname).st_size
            if real_size != expected_size:
                raise Fail("Invalid size for %s: expected %d, got %d", absname, expected_size, real_size)

        # Check the file against the checksums that we have
        for hashtype in self.FIELDS:
            hashsum = file_sums.get(hashtype, None)
            if hashsum is None: continue

            # Compute the checksum
            if hashtype == "MD5SUM":
                hasher = hashlib.md5()
            elif hashtype == "SHA256":
                hasher = hashlib.sha256()
            elif hashtype == "SHA1":
                hasher = hashlib.sha1()
            else:
                continue
            with open(absname, "rb") as fd:
                hasher.update(fd.read())

            # Verify
            if hasher.hexdigest() != hashsum:
                raise Fail("Invalid checksum for %s: expected %s, got %s", absname, hashsum, hasher.hexdigest())

    def parse_release_file(self, pathname):
        """
        Add checksums from a Release file
        """
        self.sources.append(pathname)
        with open(pathname, "rt") as fd:
            for rec in deb822.Deb822.iter_paragraphs(fd, fields=self.FIELDS):
                for hashname in self.FIELDS:
                    hashes = rec.get(hashname, None)
                    if hashes is None: continue
                    for line in hashes.split("\n"):
                        line = line.strip()
                        if not line: continue
                        hashsum, size, pathname = line.split()
                        entry = self.by_relname.get(pathname, None)
                        if entry is None:
                            self.by_relname[pathname] = { "size": int(size), hashname: hashsum }
                        else:
                            entry["size"] = int(size)
                            entry[hashname] = hashsum

    def parse_checksums_file(self, pathname, fieldname):
        """
        Add checksums from a md5sum/sha256sum format file
        """
        self.sources.append(pathname)
        with open(pathname, "rt") as fd:
            for line in fd:
                hashsum, pathname = line.split()
                if pathname.startswith("./"):
                    pathname = pathname[2:]
                entry = self.by_relname.get(pathname, None)
                if entry is None:
                    self.by_relname[pathname] = { fieldname: hashsum }
                else:
                    entry[fieldname] = hashsum


