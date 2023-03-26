from simple_cdd.exceptions import Fail
from simple_cdd.utils import run_command, Checksums
from simple_cdd.gnupg import Gnupg
from .base import Tool
from urllib.parse import urlparse, urljoin
from urllib import request
import os
import re
import logging

log = logging.getLogger()

@Tool.register
class ToolMirrorDownload(Tool):
    type = "mirror"
    name = "download"

    def __init__(self, env):
        self.env = env
        self.gnupg = Gnupg(env)

    def check_pre(self):
        super().check_pre()
        if not self.env.get("DI_WWW_HOME") and not self.env.get("custom_installer"):
            if not self.env.get("checksum_files"):
                raise Fail("Cannot run mirror/download: checksum_files is empty")
            if not self.env.get("di_match_files"):
                raise Fail("Cannot run mirror/download: di_match_files is empty")

    def run(self):
        env = self.env
        logdir = env.get("simple_cdd_logs")
        logfilename = os.path.join(logdir, "{}-{}.log".format(self.type, self.name))

        with open(logfilename, "wt") as logfd:
            baseurl = env.get("files_debian_mirror")
            path_depth = urlparse(baseurl).path.strip("/").count("/") + 1

            if env.get("http_proxy"):
                os.environ.setdefault('http_proxy', env.get("http_proxy"))

            def _download(url, output, checksums=None, relname=None):
                if checksums:
                    if os.path.exists(output):
                        try:
                            checksums.verify_file(output, relname)
                            log.debug("skipping download: %s checksum matched", output)
                            return
                        except Fail:
                            log.debug("re-downloading: %s checksum invalid", output)
                            pass
                if not os.path.isdir(os.path.dirname(output)):
                    os.makedirs(os.path.dirname(output))
                log.debug("downloading: %s", output)
                request.urlretrieve(url, filename=output)
                if checksums:
                    checksums.verify_file(output, relname)

            if env.get("mirror_files"):
                # Download the checksums present in the archive "extrafiles" and verify
                extrafiles_file_inlinesig = os.path.join(env.get("MIRROR"), "extrafiles")
                extrafiles_file= os.path.join(env.get("simple_cdd_temp"), "extrafiles.unsigned")
                download_extrafiles_file = os.path.join(env.get("files_debian_mirror"), "extrafiles")
                _download(download_extrafiles_file, extrafiles_file_inlinesig)
                self.gnupg.verify_inline_sig(extrafiles_file_inlinesig)
                self.gnupg.extract_inline_contents(extrafiles_file, extrafiles_file_inlinesig)

                # import checksums
                extrafile_sums = Checksums(self.env)
                extrafile_sums.parse_checksums_file(extrafiles_file, 'SHA256')

                with open(extrafiles_file, 'r') as ef:
                    efile = ef.readlines()
                match_mirror_files = []
                for m in env.get("mirror_files"):
                    if m.endswith('/'):
                        match_mirror_files.append(re.escape(m))
                    else:
                        match_mirror_files.append(re.escape(m) + "$")
                match_mirror_files = "(" + "|".join(match_mirror_files) + ")"
                ef_match = re.compile(match_mirror_files)
                ef_files = []
                for line in efile:
                    hashsum, relname = line.split()
                    if ef_match.match(relname):
                        ef_files.append({
                            "absname": os.path.join(env.get("MIRROR"), relname),
                            "relname": relname,
                            "url": os.path.join(env.get("files_debian_mirror"), relname),
                        })

                for x in ef_files:
                    _download(x["url"], x["absname"], checksums=extrafile_sums, relname=x["relname"])

            checksum_files = env.get("checksum_files")

            # Download files needed to build debian-installer image
            files = []
            files.extend(checksum_files)

            if checksum_files:
                # Get the release file and verify that it is valid
                release_file = os.path.join(env.get("simple_cdd_temp"), env.format("{DI_CODENAME}_Release"))
                download_release_file = os.path.join(env.get("files_debian_mirror"), "dists", env.get("DI_CODENAME"), "Release")
                _download(download_release_file, release_file)
                _download(download_release_file + ".gpg", release_file + ".gpg")
                self.gnupg.verify_detached_sig(release_file, release_file + ".gpg")

                # Parse the release file for checksums
                sums = Checksums(self.env)
                sums.parse_release_file(release_file)

                # Ensure that the checksum files are those referenced in the Release file
                # And build a list of additional files to download, matching
                # di_match_files in the checksum files contents
                di_match = re.compile(env.get("di_match_files"))
                for file in checksum_files:
                    if file.endswith("SHA256SUMS"):
                        hashtype = "SHA256"
                    elif file.endswith("MD5SUMS"):
                        hashtype = "MD5Sum"
                    else:
                        log.warn("Unknown hash type for %s, skipping file", file)
                        continue

                    separator = os.path.join('dists/', env.get("DI_CODENAME"), '')
                    separator, relname = file.split(separator)
                    absname = os.path.join(env.get("MIRROR"), file)
                    url = os.path.join(env.get("files_debian_mirror"), file)
                    # Validate the file
                    _download(url, absname, checksums=sums, relname=relname)

                    # Get the list of extra files to download: those whose
                    # pathname matches di_match
                    dirname = os.path.dirname(file)
                    extra_files = []
                    with open(absname, "rt") as fd:
                        for line in fd:
                            hashsum, relname = line.split()
                            if not di_match.search(relname): continue
                            if relname.startswith("./"): relname = relname[2:]
                            extra_files.append({
                                "absname": os.path.join(env.get("MIRROR"), dirname, relname),
                                "relname": relname,
                                "url": os.path.join(env.get("files_debian_mirror"), dirname, relname),
                            })

                    # Check downloaded files against their corresponding checksums.
                    file_sums = Checksums(self.env)
                    file_sums.parse_checksums_file(absname, hashtype)
                    for f in extra_files:
                        # Download the extra files
                        _download(f["url"], f["absname"], checksums=file_sums, relname=f["relname"])


