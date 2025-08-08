import os
import subprocess
import shutil
import re
from pathlib import Path
from graphlib import TopologicalSorter
from typing import Optional


from utils import verbose_print, check_if_file_exists

# TODO: If apt-cache | dpkg-repack is not a command, it will throw an error (FileNotFoundError)
# TODO: Use lsb_release to get the ubuntu version
# TODO: Check if removing 'recommends' packages has an effect


def repack_apt_installed_packages(
    packages: list[str], archive_dir: Path, snapshot: dict, verbose: bool = False
):
    # Create a unique target directory to save the .deb files in
    apt_dir = archive_dir / "apt"
    # Should not exist, artifact from earlier implementation
    if apt_dir.exists():
        verbose_print(verbose, f"{apt_dir} already exists. Removing it")
        shutil.rmtree(apt_dir)
    verbose_print(verbose, f"Creating {apt_dir}")
    os.mkdir(apt_dir)

    failed_packages: list[tuple[str, str]] = []
    predep_tree: dict[str, list[str]] = dict()
    name_filename_map: dict[str, str] = dict()

    for package in packages:
        # If we have processed this package before, skip it this time
        if predep_tree.get(package) is not None:
            continue
        print("-" * 10)
        # Find all dependencies and run dpkg-repack on all them
        repack_packages_recursive(
            package, apt_dir, predep_tree, name_filename_map, failed_packages, verbose
        )

    # Reformat the dependency tree to use the filenames instead of package-names
    predep_tree = reformat_predep_tree(predep_tree, name_filename_map)

    # Sort the dependency-tree
    ts = TopologicalSorter(predep_tree)
    sorted_dep_tree = ts.static_order()

    # Store the sorted dependency-tree in deps.txt
    with open(apt_dir / "deps.txt", "w") as f:
        f.write(",".join(sorted_dep_tree))

    # Init the subdictionary
    snapshot["apt"] = dict()
    # Store where the .deb-files are stored
    snapshot["apt"]["folder"] = str(apt_dir)
    # Store the errors produced when storing the packages
    # so that the user can manually supply the necessary packages to run the
    # programs.
    snapshot["apt"]["errors"] = failed_packages


def repack_packages_recursive(
    package_root: str,
    apt_dir: Path,
    predep_tree: dict[str, list[str]],
    name_filename_map: dict[str, str],
    failed_packages: list[tuple[str, str]],
    verbose: bool = False,
):
    # Init the packages list, currently only having the package root as its
    # element
    packages = [package_root]

    while len(packages):
        # Get the package to handle
        package = packages.pop()

        # If the package has been handled, continue to the next
        if predep_tree.get(package) is not None:
            continue

        # Repack the package and get its dependencies
        repack_package(
            package,
            packages,
            apt_dir,
            predep_tree,
            name_filename_map,
            failed_packages,
            verbose,
        )


# TODO: Find better name
def repack_package(
    package_name: str,
    packages: list[str],
    apt_dir: Path,
    predep_tree: dict[str, list[str]],
    name_filename_map: dict[str, str],
    failed_packages: list[tuple[str, str]],
    verbose: bool = False,
):
    # Repack the package
    verbose_print(verbose, f"Repacking {package_name}")
    output = subprocess.run(
        ["dpkg-repack", package_name], capture_output=True, cwd=apt_dir
    )
    stdout = output.stdout.decode()

    # If the stdout is empty, the command failed
    # TODO: Improve error handling, warnings are printed as stderr
    # Test this implementation
    if stdout == "":
        err = output.stderr.decode()
        # In case of an error, don't throw it, but store it.
        print(f"{package_name} could not be added:")
        print(err)
        # Store the error
        failed_packages.append((package_name, err))
        raise Exception(err)
        # Done with this package

    # Retrieve the filepath for the dependency
    search_result = re.search(
        r"dpkg-deb: building package \'(?:.+)\' in \'(.+)\'", stdout
    )
    if search_result is None:
        raise ValueError(
            f"Failed at obtaining the filepath of package {package_name}\nOutput: {stdout}"
        )
    # The first result is the entire matched string, so the capture group is at
    # index 1. If index 1 does not exist, this will produce an error
    filename = search_result.group(1)
    verbose_print(verbose, f"Filename: {filename}")
    # Store the filename mapped to the package-name
    name_filename_map[package_name] = filename

    # Get the dependencies of the package
    verbose_print(verbose, f"Getting dependencies of {package_name}")
    output = subprocess.run(
        [
            "apt-cache",
            "depends",
            "--installed",  # Only show packages actually installed on the system
            # Remove all non-essential dependencies
            "--no-suggests",
            "--no-breaks",
            "--no-replaces",
            "--no-enhances",
            "--no-conflicts",
            package_name,
        ],
        capture_output=True,
    )
    verbose_print(verbose, f"Checking dependencies of {package_name}")
    if output.returncode != 0:
        # TODO: Improve error handling
        print(f"Getting the dependencies of {package_name} failed:")
        print(output.stderr.decode())

    output_str = output.stdout.decode()
    # Regex for finding all dependencies (including recommends as these are
    # also installed by default)
    deps = re.findall(
        r"(?:(?:Depends)|(?:PreDepends)|(?:Recommends)): (.*)\n",
        output_str,
        re.MULTILINE,
    )
    # Just get the PreDepends packages
    pre_depend_deps = re.findall(
        r"PreDepends: (.*)\n",
        output_str,
        re.MULTILINE,
    )

    verbose_print(verbose, f"Dependencies: {deps}")
    # Update the dependency tree
    predep_tree[package_name] = pre_depend_deps
    # Extend the list of packages to check
    verbose_print(verbose, f"Adding dependencies to the queue")
    packages += deps
    print()


def reformat_predep_tree(
    dep_tree: dict[str, list[str]], name_filename_map: dict[str, str]
) -> dict[str, list[str]]:
    reformatted_dep_tree: dict[str, list[str]] = dict()
    for key, deps in dep_tree.items():
        # Get the filename of the given package
        package_filename = name_filename_map.get(key)
        # If the filename is None, throw an error. Unrecoverable
        if package_filename is None:
            raise Exception(f"Package missing from name_filename_map: {key}")

        # Get the filenames of the dependencies
        reformatted_deps = []
        for dep in deps:
            filename = name_filename_map.get(dep)
            # If the filename is None, throw an error. Unrecoverable
            if filename is None:
                raise Exception(f"Package missing from name_filename_map: {dep}")
            reformatted_deps.append(filename)
        # Combine to add in the reformatted dependency-tree
        reformatted_dep_tree[package_filename] = reformatted_deps
    # Return the reformatted dependency-tree
    return reformatted_dep_tree


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
