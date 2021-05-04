from simple_cdd.exceptions import Fail
from simple_cdd.utils import run_command, list_debs, shell_which
from .base import Tool, ToolShell
from debian import deb822
import shutil
import subprocess
import os
import logging

log = logging.getLogger()

@Tool.register
class ToolMirrorReprepro(ToolShell):
    type = "mirror"
    name = "reprepro"

    def run(self):
        """
        Export variables and run the script
        """
        self.check_pre()

        codename = self.env.get("CODENAME")
        di_codename = self.env.get("DI_CODENAME")

        # Distributions in our local mirror
        distributions_used = [codename]
        distributions = {
            codename: {
                "Architectures": "{ARCHES}",
                "Components": "{mirror_components}",
                "UDebComponents": "main",
                "Description": "mirror for {CODENAME}",
                "Suite": "{SUITE}",
            }
        }

        if codename != di_codename:
            distributions_used.append(di_codename)
            distributions[di_codename] = {
                "Architectures": "{ARCHES}",
                "Components": "{mirror_components}",
                "UDebComponents": "main",
                "Description": "mirror for {CODENAME}",
                "Update": "default-udebs",
                "Suite": "{SUITE}",
            }

        # Update methods for our distributions
        updates = {
            "default": {
                "Suite": "*",
                "Architectures": "{ARCHES}",
                "UDebComponents": "",
                "Method": "{debian_mirror}",
                "FilterList": "deinstall package-list",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-base": {
                "Suite": "*",
                "Architectures": "{ARCHES}",
                "UDebComponents": "",
                "Method": "{debian_mirror}",
                "FilterFormula": "priority (== required) | priority (== important) | priority (== standard)",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-udebs": {
                "Suite": "*",
                "Architectures": "{ARCHES}",
                "Components": "",
                "Method": "{debian_mirror}",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-security-legacy": {
                "Suite": "*/updates",
                "Architectures": "{ARCHES}",
                "UDebComponents": "",
                "Method": "{security_mirror}",
                "FilterList": "deinstall package-list",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-base-security-legacy": {
                "Suite": "*/updates",
                "Architectures": "{ARCHES}",
                "UDebComponents": "",
                "Method": "{security_mirror}",
                "FilterFormula": "priority (== required) | priority (== important) | priority (== standard)",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-security": {
                "Suite": "{CODENAME}-security",
                "Architectures": "{ARCHES}",
                "UDebComponents": "",
                "Method": "{security_mirror}",
                "FilterList": "deinstall package-list",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-base-security": {
                "Suite": "{CODENAME}-security",
                "Architectures": "{ARCHES}",
                "UDebComponents": "",
                "Method": "{security_mirror}",
                "FilterFormula": "priority (== required) | priority (== important) | priority (== standard)",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-updates": {
                "Suite": "{CODENAME}-updates",
                "Architectures": "{ARCHES}",
                "UDebComponents": "main",
                "Method": "{updates_mirror}",
                "FilterList": "deinstall package-list",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-base-updates": {
                "Suite": "{CODENAME}-updates",
                "Architectures": "{ARCHES}",
                "UDebComponents": "main",
                "Method": "{updates_mirror}",
                "FilterFormula": "priority (== required) | priority (== important) | priority (== standard)",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-extra": {
                "Suite": "*",
                "Architectures": "{ARCHES}",
                "Components": "{mirror_components_extra}",
                "UDebComponents": "{mirror_udebcomponents_extra}",
                "Method": "{debian_mirror_extra}",
                "FilterList": "deinstall package-list",
                "VerifyRelease": "{verify_release_keys}",
                "ListShellHook": "{debian_mirror_extra_list_shell_hook}",
            },
            "default-proposed-updates": {
                "Suite": "{CODENAME}-proposed-updates",
                "Architectures": "{ARCHES}",
                "UDebComponents": "main",
                "Method": "{debian_mirror}",
                "FilterList": "deinstall package-list",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-base-proposed-updates": {
                "Suite": "{CODENAME}-proposed-updates",
                "Architectures": "{ARCHES}",
                "UDebComponents": "main",
                "Method": "{debian_mirror}",
                "FilterFormula": "priority (== required) | priority (== important) | priority (== standard)",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-profiles-udeb": {
                "Suite": "{profiles_udeb_dist}",
                "Architectures": "{ARCHES}",
                "Components": "",
                "FilterFormula": "package (== simple-cdd-profiles)",
                "Method": "{debian_mirror}",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-extra-udebs": {
                "Suite": "{extra_udeb_dist}",
                "Architectures": "{ARCHES}",
                "Components": "",
                "Method": "{debian_mirror}",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-backports": {
                "Suite": "{CODENAME}-backports",
                "Architectures": "{ARCHES}",
                "UDebComponents": "main",
                "Method": "{backports_mirror}",
                "FilterList": "deinstall backports-packages",
                "VerifyRelease": "{verify_release_keys}",
            },
            "default-backports-filter-formula": {
                "Suite": "{CODENAME}-backports",
                "Architectures": "{ARCHES}",
                "UDebComponents": "main",
                "Method": "{backports_mirror}",
                "FilterFormula": "{backports_filter_formula}",
                "VerifyRelease": "{verify_release_keys}",
            },
        }

        updates_used = ["default", "default-base", "default-udebs"]
        if self.env.get("clean_mirror"):
            # invoke reprepro's "magic delete" rule.
            updates_used.append("-")
        if self.env.get("security_mirror"):
            if codename == "buster" or codename == "stretch" or codename == "jessie":
                updates_used.append("default-base-security-legacy")
                updates_used.append("default-security-legacy")
            else:
                updates_used.append("default-base-security")
                updates_used.append("default-security")
        if self.env.get("debian_mirror_extra"):
            updates_used.append("default-extra")
            if self.env.get("debian_mirror_extra_dist"):
                updates["default-extra"]["Suite"] = "{debian_mirror_extra_dist}"
        if self.env.get("proposed_updates"):
            updates_used.append("default-base-proposed-updates")
            updates_used.append("default-proposed-updates")
        if self.env.get("updates_mirror"):
            updates_used.append("default-base-updates")
            updates_used.append("default-updates")
        if self.env.get("profiles_udeb_dist"):
            updates_used.append("default-profiles-udeb")
        if self.env.get("extra_udeb_dist"):
            updates_used.append("default-extra-udebs")
            filter = []
            for p in self.env.get("extra_udeb_dist_packages"):
                filter.append("package (== {})".format(p))
            updates["default-extra-udebs"]["FilterFormula"] = " | ".join(filter)
        if self.env.get("backports"):
            updates_used.append("default-backports")
            if self.env.get("backports_filter_formula"):
                updates_used.append("default-backports-filter-formula")
        if self.env.get("udebs_filter_formula"):
            updates["default-udebs"]["FilterFormula"] = "{udebs_filter_formula}"

        distributions[codename]["Update"] = " ".join(updates_used)

        confdir = os.path.join(self.env.get("MIRROR"), "conf")
        os.makedirs(confdir, exist_ok=True)

        def print_records(confname, name_field, field_order, records_used, records):
            verify_release_keys = "|".join(self.env.get("verify_release_keys"))
            with open(os.path.join(confdir, confname), "wt") as fd:
                for name in records_used:
                    rec = records[name]
                    print("{}: {}".format(name_field, name), file=fd)
                    for field in field_order:
                        val = rec.get(field, None)
                        if val is None: continue
                        print("{}: {}".format(field, self.env.format(val, verify_release_keys=verify_release_keys)), file=fd)
                    print(file=fd)

        # Generate the conf/distributions file
        field_order = ["Architectures", "Components", "UDebComponents", "Description", "Update", "Suite"]
        print_records("distributions", "Codename", field_order, distributions_used, distributions)

        # Generate the conf/updates file
        field_order = ["Suite", "Architectures", "Components", "UDebComponents", "Method", "FilterList", "FilterFormula", "VerifyRelease", "ListShellHook"]
        print_records("updates", "Name", field_order, updates_used, updates)

        # Generate the conf/backport-packages file
        if self.env.get("backports"):
            with open(os.path.join(confdir, "backports-packages"), "wt") as fd:
                packages = set(self.env.get("backports_packages"))
                for package in sorted(packages):
                    print(package, "install", file=fd)

        # Recreate an empty package-list file
        pkglist_file = os.path.join(confdir, "package-list")
        with open(pkglist_file, "wt") as fd:
            pass

        # Build the environment for running reprepro
        reprepro_env = {}
        for name, val, changed in self.env.export_iter():
            reprepro_env[name] = str(val)

        # include local packages into the mirror
        for src in self.env.get("local_packages"):
            for f in list_debs(src):
                if f.endswith(".deb"):
                    cmd = ["reprepro"]
                    cmd.extend(self.env.get("reprepro_opts"))
                    cmd.extend(["--ignore=wrongdistribution", "includedeb", codename, f])
                    retval = run_command("reprepro: including local deb file", cmd, env=reprepro_env)
                    if retval != 0:
                        raise Fail("reprepro failed with exit code: %d", retval)
                elif f.endswith(".udeb"):
                    cmd = ["reprepro"]
                    cmd.extend(self.env.get("reprepro_opts"))
                    cmd.extend(["--ignore=wrongdistribution", "includeudeb", codename, f])
                    retval = run_command("reprepro: including local deb file", cmd, env=reprepro_env)
                    if retval != 0:
                        raise Fail("reprepro failed with exit code: %d", retval)
                    if codename != di_codename:
                        cmd = ["reprepro"]
                        cmd.extend(self.env.get("reprepro_opts"))
                        cmd.extend(["--ignore=wrongdistribution", "includeudeb", di_codename, f])
                        retval = run_command("reprepro: including local deb file", cmd, env=reprepro_env)
                else:
                    log.warn("unknown package type: %s", f)

        # Update package lists
        cmd = ["reprepro"]
        cmd.extend(self.env.get("reprepro_opts"))
        cmd.extend(["--noskipold", "update"])
        retval = run_command("reprepro: updating package lists", cmd, env=reprepro_env)
        if retval != 0:
            raise Fail("reprepro failed with exit code: %d", retval)

        # TODO: we can compute here via dose-debcheck if $all_packages are all
        # installable, and warn otherwise or fail before we start building a
        # mirror

        self.run_script()

        for f in self.env.get("exclude_files"):
            with open(f, "rt") as infd:
                for line in infd:
                    pkg = line.strip()
                    if not pkg or pkg.startswith("#"): continue
                    # Remove files listed in exclude_files
                    cmd = ["reprepro"]
                    cmd.extend(self.env.get("reprepro_opts"))
                    cmd.extend(["--noskipold", "remove", self.env.get("CODENAME"), pkg])
                    retval = run_command("reprepro: remove console-tools-freebsd", cmd, env=reprepro_env)
                    if retval != 0:
                        raise Fail("reprepro failed with exit code: %d", retval)

        self.check_post(retval)

    def check_post(self, retval):
        debcheck = shell_which("dose-debcheck")
        if debcheck is None:
            log.info("dose-debcheck not found: skipping mirror checks")
            return

        for a in self.env.get("ARCHES"):
            mirror_components = self.env.get("mirror_components")
            for component in mirror_components:

                bg_pkgfile = [
                    self.env.format(
                        "{MIRROR}/dists/{CODENAME}/{component}/binary-{a}/Packages",
                        component=i, a=a)
                    for i in mirror_components if i != component
                ]

                bg_command = []
                for file in bg_pkgfile:
                    bg_command.append('--bg')
                    bg_command.append(file)

                command = [debcheck, "--failures", "--explain"]
                command.extend(bg_command)
                pkgfile = self.env.format(
                    "{MIRROR}/dists/{CODENAME}/{component}/binary-{a}/Packages",
                    component=component, a=a)
                if os.stat(pkgfile).st_size == 0: continue
                log.info("Checking package file %s using %s", pkgfile, debcheck)
                command.append(pkgfile)

                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                retval = proc.wait()
                if retval != 0:
                    log.warn("Found uninstallable packages in %s:", pkgfile)
                    for line in stdout.decode("utf-8").split("\n"):
                        log.warn("  %s", line)



