import shutil
import tomllib
import datetime
import re
import subprocess
import json
import uuid
import os
from pathlib import Path
from typing import Optional

from utils import (
    check_if_file_exists,
    check_subprocess_error,
    create_absolute_path,
    verbose_print,
    check_tool_existence,
)
from apt_deps import repack_apt_installed_packages


# ====================================================================================
# Snapshot
# ====================================================================================


def snapshot(tomlfile_path_str: str, verbose: bool = False):
    """Create snapshot from TOML-file

    ---
    Args:
        tomlfile_path_str : `str`
            Filepath to the TOML-file to load the snapshot from

        verbose : `bool`, default 'False'
            Enable verbose printing
    ---
    Returns:
        None
    """
    # Check if the dependencies of the script are available on the system
    check_script_dependencies()

    snapshot = dict()

    # Resolve the TOML-file path
    tomlfile_path = Path(tomlfile_path_str).expanduser().resolve()

    print()
    print("TOML:")
    # Check if TOML-file exists
    verbose_print(verbose, f"Looking for TOML-file at '{tomlfile_path}'")
    exists, err_msg = check_if_file_exists(tomlfile_path)
    if not exists:
        raise FileNotFoundError(err_msg)
    print(f"Found TOML-file at '{tomlfile_path}'")
    # Open the TOML-file if it exists
    with open(tomlfile_path, "rb") as f:
        config = tomllib.load(f)

    # Add the name of snapshot to the lockfile
    name = config.get("name")
    if name is None:
        raise ValueError(f"The key 'name' is missing from {tomlfile_path.name}")
    snapshot["name"] = name

    # Set the working directory, the directory where the TOML-file resides
    work_dir = tomlfile_path.parent

    # Create a temporary directory to use as the root of the zip-archive while
    # creating it
    archive_dir = work_dir / ("tmp-" + str(uuid.uuid4()))
    os.mkdir(archive_dir)

    # Create filename for zip-file
    date = str(datetime.date.today())
    name = name + "-" + date
    zip_path = work_dir / f"{name}"
    zip_file = zip_path.with_suffix(".zip")

    # Set the lockfile-path
    lockfile_path = archive_dir / "ugle.lock"

    # Surround the following in a try-block so we can clean up in case an error
    # is thrown
    try:
        # If there is a Spack entry, handle it
        spack_config = config.get("spack")
        if spack_config is not None:
            spack_deps(spack_config, snapshot, work_dir, tomlfile_path, verbose)

        # Other dependencies
        deps = config.get("deps")
        if deps is not None:
            print()
            print("=" * 20)
            print("LOCAL DEPENDENCIES:")
            print()
            handle_other_deps(deps, snapshot, work_dir, archive_dir, verbose)

        # Load docker-helpers into the snapshot
        load_docker_helpers(snapshot, verbose)

        # Handle apt installed packages
        apt_packages = config.get("apt")
        if apt_packages is not None:
            print()
            print("=" * 20)
            print("APT PACKAGES:")
            repack_apt_installed_packages(apt_packages, archive_dir, snapshot, verbose)
            # Copy the install script to the apt-folder
            shutil.copyfile(
                Path(__file__).parent / "exports" / "install.sh",
                archive_dir / "apt" / "install.sh",
            )

        # Create the lockfile and store the snapshot in it
        with open(lockfile_path, "w") as f:
            json.dump(snapshot, f)

        # Copy the TOML-file into the archive
        shutil.copyfile(tomlfile_path, archive_dir / "ugle.toml")

        print()
        print("=" * 20)
        print("ZIP")
        # If the zip-file already exists, overwrite it
        if zip_file.exists():
            print(f"'{zip_file}' already exists. Will overwrite")
            os.remove(zip_file)

        # TODO: Error handling
        verbose_print(verbose, f"Creating zip-file at '{zip_file}'")
        shutil.make_archive(str(zip_path), format="zip", root_dir=str(archive_dir))

    finally:
        # When everything has been run, remove the archive directory regardless
        # of errors thrown
        verbose_print(verbose, "")
        verbose_print(verbose, "=" * 20)
        verbose_print(verbose, f"Cleaning up '{archive_dir}'")
        shutil.rmtree(archive_dir)

    print()
    print("#" * 60)
    print(f"Snapshot stored in {zip_path}.zip")
    print("#" * 60)


def spack_deps(
    spack_config: dict[str, str],
    snapshot: dict,
    work_dir: Path,
    tomlfile_path: Path,
    verbose: bool = False,
):
    """
    Handle dependencies installed with Spack

    ---
    Args:
        spack_config : `dict[str, str]`
            The Spack config loaded from the TOML-file

        snapshot : `dict`
            The snapshot dictionary to be dumped. Will be modified inside the function

        work_dir: `Path`
            The parent directory of the TOML-file the current snapshot is based on

        tomlfile_path: `Path`
            Filepath to the TOML-file the current snapshot is based on

        verbose: `bool`, default 'False'
            Enable verbose printing

    ---
    Returns:
        None
    """
    # This should exist
    print()
    print("SPACK:")
    lockfile_str = spack_config.get("lockfile")
    if lockfile_str is None:
        raise KeyError(f"No attribute called 'lockfile' in '{tomlfile_path}'")
    lockfile_path = Path(lockfile_str)

    # Resolves the path to an absolute path
    lockfile_path = create_absolute_path(lockfile_path, work_dir)
    verbose_print(verbose, f"Looking for spack lockfile in: {lockfile_path}")
    exists, err_msg = check_if_file_exists(lockfile_path)
    if not exists:
        raise FileNotFoundError(err_msg)

    # Extract the contents of the lockfile
    verbose_print(verbose, f"Loading contents of '{lockfile_path}'")
    with open(lockfile_path, "r") as f:
        lockfile_content = json.load(f)

    print(f"Storing contents of '{lockfile_path}' in snapshot")
    # Store the contents of the lockfile in the snapshot
    snapshot["spack"] = lockfile_content


def handle_other_deps(
    deps: dict[str, dict[str, str]],
    snapshot: dict,
    work_dir: Path,
    archive_dir: Path,
    verbose: bool = False,
):
    """Handle local dependencies not installed by Spack

    ---
    Args:
        deps : `dict[str, dict[str, str]]`
            The local dependencies to take snapshot of. Structured as
            { <dep-name>: { "filepath": <filepath>, "url": <url>, ... }, ... }

        snapshot : `dict`
            The snapshot dictionary to be dumped. Will be modified inside the function

        work_dir: `Path`
            The parent directory of the TOML-file the current snapshot is based on

        archive_dir: `Path`
            The directory where the archive is being created before it gets
            zipped

        verbose : `bool`, default 'False'
            Enable verbose printing

    ---
    Returns:
        None
    """
    # deps structure:
    # deps = { <dep-name>: {filepath: <file>, url: <url>}, <dep-2>: {filepath: <file>, url: <url>}}
    snapshot["deps"] = dict()
    for dep_name, dep in deps.items():
        filepath = dep.get("filepath")
        url = dep.get("url")
        copy = dep.get("copy")
        if copy is None:
            copy = True

        if filepath is not None:
            if copy:
                local_dep_copy(
                    dep_name, filepath, snapshot, work_dir, archive_dir, verbose
                )
            else:
                local_dep_git(dep_name, filepath, snapshot, work_dir, url, verbose)
        else:
            raise KeyError(
                f"The dependency {dep_name} does not supply a filepath nor an url."
            )


def local_dep_copy(
    name: str,
    filepath_str: str,
    snapshot: dict,
    work_dir: Path,
    archive_dir: Path,
    verbose: bool = False,
):
    """
    Add local dependency to the snapshot. The dependency is copied into the
    archive directory.

    ---
    Args:
        name : `str`
            Name of the dependency

        filepath_str : `str`
            The filepath to the dependency

        snapshot : `dict`
            The snapshot dictionary to be dumped. Will be modified inside the function

        work_dir: `Path`
            The parent directory of the TOML-file the current snapshot is based on

        archive_dir: `Path`
            The directory where the archive is being created before it gets
            zipped

        verbose : `bool`, default 'False'
            Enable verbose printing

    ---
    Returns:
        None
    """
    filepath = create_absolute_path(Path(filepath_str), work_dir)
    print("-" * 30)
    print(f"Snapshot of '{name}' (BY COPY): ")
    print(f"Looking for {name} in '{filepath}'")
    if not filepath.exists():
        raise FileNotFoundError(f"Filepath '{filepath}' does not exist")
    if not filepath.is_dir():
        raise Exception(f"Filepath '{filepath}' is not a directory")

    dest = archive_dir / name
    verbose_print(verbose, f"Destination: {dest}")
    if dest.exists():
        verbose_print(verbose, f"{dest} already exists. Creating new destination-name")
        dest.with_name(dest.name + "-" + str(uuid.uuid4()))

    # Copy the dependency to the temporary folder that is to be zipped
    verbose_print(verbose, f"Copy '{filepath}' to '{dest}'")
    output = subprocess.run(["cp", "-r", filepath, dest], capture_output=True)
    check_subprocess_error(output)

    # Set copy to True in snapshot
    snapshot["deps"][name] = {
        "copy": True,
    }


def local_dep_git(
    name: str,
    filepath_str: str,
    snapshot: dict,
    work_dir: Path,
    url: Optional[str],
    verbose: bool = False,
):
    """
    Add local dependency to the snapshot. The dependency is assumed to be a local git repo and
    referenced by its commit hash.

    ---
    Args:
        name : `str`
            Name of the dependency

        filepath_str : `str`
            The filepath to the dependency

        snapshot : `dict`
            The snapshot dictionary to be dumped. Will be modified inside the function

        work_dir: `Path`
            The parent directory of the TOML-file the current snapshot is based on

        url : `Optional[str]`
            The git url for the dependency, if it exists

        verbose : `bool`, default 'False'
            Enable verbose printing

    ---
    Returns:
        None
    """
    filepath = create_absolute_path(Path(filepath_str), work_dir)
    print("-" * 30)
    print(f"Snapshot of '{name}' (BY GIT): ")
    print(f"Looking for {name} in {filepath}")
    if not filepath.exists():
        raise FileNotFoundError(f"Filepath {filepath} does not exist")
    if not filepath.is_dir():
        raise Exception(f"Filepath {filepath} is not a directory")

    # Get git status of the repo at <filepath>
    git_status = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, cwd=filepath
    )
    check_subprocess_error(git_status, filepath)

    verbose_print(verbose, "" * 4)
    verbose_print(verbose, "Checking the working tree")
    if git_status.stdout.decode() != "":
        print()
        print("*" * 90)
        print("WARNING!")
        print(f"The working tree of {filepath} is not clean:")
        print(git_status.stdout.decode())
        print("NOTE: Only committed changes will be added to the snapshot.")
        print("*" * 90)
    else:
        verbose_print(verbose, "Working tree is clean")

    verbose_print(verbose, "" * 4)
    verbose_print(verbose, "Getting commit-hash")
    # Get the commit-hash of the commit currently being checked out
    output = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, cwd=filepath
    )
    check_subprocess_error(output, filepath)
    commit_hash = output.stdout.decode().strip()
    verbose_print(verbose, f"Commit-hash: {commit_hash}")

    # If url is not defined, try to get it from 'git remove -v'
    verbose_print(verbose, "" * 4)
    if url is None:
        verbose_print(verbose, "Trying to get url with 'git remote -v'")

        remote_cmd = subprocess.run(
            ["git", "remote", "-v"], capture_output=True, cwd=filepath
        )
        check_subprocess_error(remote_cmd, filepath)
        # Regex for getting the remote url. We pick the push url since this is
        # most likely to contain new updates
        url_remote_cmd = re.findall(
            r"^origin\t(.*) \(push\)", remote_cmd.stdout.decode(), re.MULTILINE
        )
        # Check if a match was made
        if len(url_remote_cmd) > 0:
            # At least one match has been made, so we pick the first one. Can
            # not see how multiple matches could be made.
            url = url_remote_cmd[0]

            verbose_print(verbose, f"Found url: {url}")
        else:
            verbose_print(verbose, "Did not find url")
    else:
        verbose_print(verbose, f"url: {url}")

    print()
    print(f"Adding {name} to snapshot")

    # If there a url exists, add it to the lockfile
    if url is not None:
        snapshot["deps"][name] = {
            "filepath": str(filepath),
            "hash": commit_hash,
            "copy": False,
            "url": url,
        }
    else:
        snapshot["deps"][name] = {
            "filepath": str(filepath),
            "hash": commit_hash,
            "copy": False,
        }


def load_docker_helpers(snapshot: dict, verbose: bool = False):
    """
    Load the helperfiles for creating the 'Dockerfile' and 'docker-compose.yaml'
    when checking out the snapshot. They get loaded into the snapshot dictionary

    ---
    Args:
        snapshot : `dict`
            The snapshot dictionary to be dumped. Will be modified inside the function

        verbose : `bool`, default 'False'
            Enable verbose printing

    ---
    Returns:
        None
    """
    # Create the path to the local exports folder
    local_exports_path = Path(__file__).parent / "exports"
    # Retrieve head and tail of Dockerfile
    # (Everything except the volume-declarations)
    with open(local_exports_path / "Dockerfile-head.txt", "r") as f:
        docker_head = f.read()
    with open(local_exports_path / "Dockerfile-tail.txt", "r") as f:
        docker_tail = f.read()
    # Get the docker-compose helper
    with open(local_exports_path / "docker-compose.yaml", "r") as f:
        docker_compose = f.read()

    snapshot["dockerhead"] = docker_head
    snapshot["dockertail"] = docker_tail
    snapshot["docker-compose"] = docker_compose


def check_script_dependencies():
    """
    Check if the scripts dependencies are available at the system the program is
    to be run on. If they are not an error is thrown.

    ---
    Returns:
        None
    """
    check_tool_existence("git")
    check_tool_existence("dpkg-repack")
    check_tool_existence("cp")
