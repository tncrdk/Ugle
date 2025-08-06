import os
import subprocess
import shutil
import uuid
import re
from pathlib import Path
from typing import Optional


from utils import verbose_print, check_if_file_exists

# TODO: If apt-cache | dpkg-repack is not a command, it will throw an error (FileNotFoundError)


def get_apt_installed_packages(
    packages: list[str], tomlfile_path: Path, snapshot: dict, verbose: bool = False
):
    # Create a unique target directory to save the .deb files in
    apt_dir = Path(tomlfile_path.stem + "-" + str(uuid.uuid4())).resolve()
    if apt_dir.exists():
        verbose_print(verbose, f"{apt_dir} already exists. Removing it")
        shutil.rmtree(apt_dir)
    verbose_print(verbose, f"Creating {apt_dir}")
    os.mkdir(apt_dir)

    processed_packages = set()
    failed_packages: list[tuple[str, str]] = []
    while len(packages) > 0:
        package = packages[0]
        # Remove the package from the list
        packages.pop(0)

        # If we have processed this package before, skip it this time
        if package in processed_packages:
            continue

        # Repack the local dependency and store the package in target_dir
        verbose_print(verbose, f"Adding {package}")
        output = subprocess.run(
            ["dpkg-repack", package], capture_output=True, cwd=apt_dir
        )
        err = output.stderr.decode()
        # In case of an error, don't throw it, but store it.
        if err != "":
            # TODO: Improve error handling, warnings are printed as stderr
            print(f"{package} could not be added")
            failed_packages.append((package, err))

        print(output.stdout.decode())
        # Add package to the set of processed packages
        processed_packages.add(package)

        # Get the dependencies of the package
        verbose_print(verbose, f"Checking dependencies of {package}")
        output = subprocess.run(["apt-cache", "depends", package], capture_output=True)
        if output.returncode != 0:
            # TODO: Improve error handling
            print(f"Getting the dependencies of {package} failed:")
            print(output.stderr.decode())
            continue

        output_str = output.stdout.decode()
        # '(?:Pre)?Depends' to include both PreDepends and Depends
        dependencies = re.findall(r"(?:Pre)?Depends: (.*)\n", output_str, re.MULTILINE)
        # Concatenate the new-found dependencies with the packages list
        packages = dependencies + packages

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


if __name__ == "__main__":
    snapshot = dict()
    get_apt_installed_packages(
        ["python3"], Path("ugle.toml").resolve(), snapshot, verbose=True
    )
    print(snapshot)
