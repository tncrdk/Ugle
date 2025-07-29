import tomllib
import datetime
import os
import re
import subprocess
import json
from pathlib import Path
from typing import Optional

from utils import check_if_file_exists, create_absolute_path, verbose_print

# TODO: Document exceptions

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
    # Copy spack lockfile (if exists)
    # store commit hash and either url or filepath to all other deps

    snapshot = dict()

    # Resolve the TOML-file path
    tomlfile_path = Path(tomlfile_path_str).expanduser().resolve()

    # Check if TOML-file exists
    verbose_print(verbose, f"Looking for TOML-file at {tomlfile_path}")
    exists, err_msg = check_if_file_exists(tomlfile_path)
    if not exists:
        raise FileNotFoundError(err_msg)
    verbose_print(verbose, f"Found TOML-file at {tomlfile_path}\n")
    # Open the TOML-file if it exists
    with open(tomlfile_path, "rb") as f:
        config = tomllib.load(f)

    # Create the working directory, the directory where the TOML-file resides
    work_dir = tomlfile_path.parent

    # Add the name of snapshot to the lockfile
    name = config.get("name")
    if name is None:
        raise ValueError(f"The key 'name' is missing from {tomlfile_path.name}")
    date = str(datetime.date.today())
    snapshot["name"] = name + "-" + date

    # If there is a Spack entry, handle it
    spack_config = config.get("spack")
    if spack_config is not None:
        spack_deps(spack_config, snapshot, work_dir, tomlfile_path, verbose)

    # TODO: Handle current folder project

    # Other dependencies
    deps = config.get("deps")
    if deps is None:
        # deps = {"work_dir": {"filepath": "."}}
        deps = dict()
    # else:
    #     deps["work_dir"] = {"filepath": "."}

    handle_other_deps(deps, snapshot, work_dir, verbose)

    os.chdir(work_dir)
    with open("ugle.lock", "w") as f:
        json.dump(snapshot, f)

    print()
    # print("#" * 10)
    print("DONE!")


def spack_deps(
    spack_config: dict[str, str],
    snapshot: dict,
    work_dir: Path,
    tomlfile_path: Path,
    verbose: bool = False,
):
    """Handle dependencies installed with Spack

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
    lockfile_str = spack_config.get("lockfile")
    if lockfile_str is None:
        raise KeyError(f"No attribute called 'lockfile' in {tomlfile_path}.")
    lockfile_path = Path(lockfile_str)

    # Resolves the path to an absolute path
    lockfile_path = create_absolute_path(lockfile_path, work_dir)
    verbose_print(verbose, f"Looking for spack lockfile in: {lockfile_path}")
    exists, err_msg = check_if_file_exists(lockfile_path)
    if not exists:
        raise FileNotFoundError(err_msg)

    # Extract the contents of the lockfile
    verbose_print(verbose, f"Loading contents of {lockfile_path}")
    with open(lockfile_path, "r") as f:
        lockfile_content = json.load(f)

    verbose_print(verbose, f"Storing contents of {lockfile_path} in snapshot")
    # Store the contents of the lockfile in the snapshot
    snapshot["spack"] = lockfile_content


def handle_other_deps(
    deps: dict[str, dict[str, str]],
    snapshot: dict,
    work_dir: Path,
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

        if filepath is not None:
            local_dep(dep_name, filepath, snapshot, work_dir, url, verbose)
        else:
            raise KeyError(
                f"The dependency {dep_name} does not supply a filepath nor an url."
            )


def local_dep(
    name: str,
    filepath_str: str,
    snapshot: dict,
    work_dir: Path,
    url: Optional[str],
    verbose: bool = False,
):
    """Add local dependency to the snapshot dictionary. The dependency is assumed to be a local git repo.

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
    verbose_print(verbose, "=" * 10)
    verbose_print(verbose, f"Looking for {name} in {filepath}")
    if not filepath.exists():
        raise FileNotFoundError(f"Filepath {filepath} does not exist")
    os.chdir(filepath)

    git_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True)
    # If something goes wrong with the above command, it needs to be fixed
    if not git_status.returncode == 0:
        # TODO: Create better exception type and error message. Ex: which dep
        # gave the error
        raise Exception(git_status.stderr.decode())

    verbose_print(verbose, "-" * 4)
    verbose_print(verbose, "Checking the working tree")
    if git_status.stdout.decode() != "":
        print(f"The working tree of {filepath} is not clean:")
        print(git_status.stdout.decode())
        while True:
            print(
                "Do you want to continue creating a snapshot? Note that only committed changes will be added to the snapshot."
            )
            ans = input("[y/n]: ").strip()
            if ans == "y":
                break
            elif ans == "n":
                # TODO: Create better error to be handled further up the call
                # stack
                raise SystemExit("Snapshot aborted")

            print("Not valid")
    else:
        verbose_print(verbose, "Working tree is clean")

    verbose_print(verbose, "-" * 4)
    verbose_print(verbose, "Getting commit-hash")
    # Get the commit-hash of the commit currently being check out
    commit_hash = (
        subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True)
        .stdout.decode()
        .strip()
    )
    verbose_print(verbose, f"Commit-hash: {commit_hash}")
    verbose_print(verbose, "-" * 4)

    # If url is not defined, try to get it from 'git remove -v'
    if url is None:
        verbose_print(verbose, "Trying to get url with 'git remote -v'")

        remote_cmd = subprocess.run(["git", "remote", "-v"], capture_output=True)
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

    verbose_print(verbose, f"-" * 4)
    verbose_print(verbose, f"Adding {name} to snapshot")

    # If there a url exists, add it to the lockfile
    if url is not None:
        snapshot["deps"][name] = {
            "filepath": str(filepath),
            "hash": commit_hash,
            "url": url,
        }
    else:
        snapshot["deps"][name] = {
            "filepath": str(filepath),
            "hash": commit_hash,
        }
