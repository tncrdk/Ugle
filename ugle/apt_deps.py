import os
import subprocess
import shutil
import uuid
import re
from pathlib import Path
from typing import Optional


from utils import verbose_print, check_if_file_exists

# TODO: If apt-cache | dpkg-repack is not a command, it will throw an error (FileNotFoundError)
# TODO: Use lsb_release to get the ubuntu version


def repack_apt_installed_packages(
    packages: list[str], archive_dir: Path, snapshot: dict, verbose: bool = False
) -> Path:
    # Create a unique target directory to save the .deb files in
    apt_dir = archive_dir / "apt"
    # Should not exist, artifact from earlier implementation
    if apt_dir.exists():
        verbose_print(verbose, f"{apt_dir} already exists. Removing it")
        shutil.rmtree(apt_dir)
    verbose_print(verbose, f"Creating {apt_dir}")
    os.mkdir(apt_dir)

    processed_packages = set()
    failed_packages: list[tuple[str, str]] = []

    for package in packages:
        print("-" * 10)

        # If we have processed this package before, skip it this time
        if package in processed_packages:
            continue

        # Get the dependencies of the package
        verbose_print(verbose, f"Checking dependencies of {package}")
        output = subprocess.run(
            [
                "apt-cache",
                "depends",
                "--installed",  # Only show packages actually installed on the system
                "--recurse",  # Recursive down through dependencies
                # Remove all non-essential dependencies
                "--no-suggests",
                "--no-breaks",
                "--no-replaces",
                "--no-enhances",
                "--no-conflicts",
                package,
            ],
            capture_output=True,
        )
        if output.returncode != 0:
            # TODO: Improve error handling
            print(f"Getting the dependencies of {package} failed:")
            print(output.stderr.decode())
            continue

        output_str = output.stdout.decode()
        # Regex for finding all dependencies (including recommends as these are
        # also installed by default)
        deps = re.findall(
            r"(?:(?:Depends)|(?:PreDepends)|(?:Recommends)): (.*)\n",
            output_str,
            re.MULTILINE,
        )
        # Add the main package as well so that we run dpkg-repack on it as well
        deps.append(package)

        # Run dpkg-repack on all the packages
        repack_packages(deps, apt_dir, processed_packages, failed_packages, verbose)

    # Init the subdictionary
    snapshot["apt"] = dict()
    # Store where the .deb-files are stored
    snapshot["apt"]["folder"] = str(apt_dir)
    # Store the errors produced when storing the packages
    # so that the user can manually supply the necessary packages to run the
    # programs.
    snapshot["apt"]["errors"] = failed_packages

    # Zip the files

    # Remove the temporary directory after zipping everything (Add it to
    # command_list?)
    # shutil.rmtree(apt_dir)
    return apt_dir


def repack_packages(
    packages: list[str],
    apt_dir: Path,
    processed_packages: set[str],
    failed_packages: list[tuple[str, str]],
    verbose: bool = False,
):
    for package in packages:
        if package in processed_packages:
            continue
        verbose_print(verbose, f"Adding {package}")
        output = subprocess.run(
            ["dpkg-repack", package], capture_output=True, cwd=apt_dir
        )
        err = output.stderr.decode()
        # In case of an error, don't throw it, but store it.
        if err != "":
            # TODO: Improve error handling, warnings are printed as stderr
            print(f"{package} could not be added:")
            print(err)
            failed_packages.append((package, err))
        else:
            print(output.stdout.decode())
        # Add package to the set of processed packages
        processed_packages.add(package)


if __name__ == "__main__":
    snapshot = dict()
    apt_dir = repack_apt_installed_packages(
        ["cmake", "python3", "libgotools-core-dev"],
        # ["tzdata"],
        Path("ugle.toml").resolve(),
        snapshot,
        verbose=True,
    )
    print(apt_dir)
    print(snapshot)
