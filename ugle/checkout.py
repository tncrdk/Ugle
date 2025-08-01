import json
import tomllib
import shutil
import os
import subprocess
from pathlib import Path
from typing import Optional

from utils import verbose_print, check_if_file_exists

# TODO: Test to clone from private repos

# ====================================================================================
# Checkout
# ====================================================================================


def checkout(
    lockfile_path_str: str,
    destination_path_str: Optional[str],
    force: bool = False,
    verbose: bool = False,
):
    """
    Checkout the projects as defined in the lock-file. A spack.lock
    file will be created there as well if necessary
    All local dependencies will be recreated
    at `~/.ugle/` unless `destination_path_str` is supplied

    ---
    Args:
        lockfile_path_str : `str`
            The filepath to the lockfile we will use to load the snapshot from

        destination_path_str : `Optional[str]`
            Alternative destination to recreate the snapshot. If not supplied, the snapshot
            will be created at `~/.ugle/`

        force : `bool`, default=False
            If force is supplied, necessary files and folders will be overwritten for the checkout to succeed

        verbose : `bool`, default=False
            Enable verbose printing

    ---
    Returns:
        None
    """
    # Copy spack lockfile (if exists)
    # store commit hash and either url or filepath to all other deps

    # Resolve the lockfile path
    lockfile_path = Path(lockfile_path_str).expanduser().resolve()

    # Check if the lockfile exists
    verbose_print(verbose, f"Looking for lockfile at {lockfile_path}")
    exists, err_msg = check_if_file_exists(lockfile_path)
    if not exists:
        raise FileNotFoundError(err_msg)
    verbose_print(verbose, f"Found lockfile at {lockfile_path}\n")
    # Open the lockfile
    with open(lockfile_path, "r") as f:
        config = json.load(f)

    # Create TOML filepath based on the lockfile
    tomlfile_path = lockfile_path.with_suffix(".toml")

    verbose_print(verbose, f"Looking for TOML-file at {tomlfile_path}")
    # Check if the TOML file exists
    exists, err_msg = check_if_file_exists(tomlfile_path)
    if exists:
        # Open the TOML file if it exists
        verbose_print(verbose, f"Found TOML-file at {tomlfile_path}")
        with open(tomlfile_path, "rb") as f:
            toml_config = tomllib.load(f)
    else:
        # Default to empty dict if the TOML file does not exist
        verbose_print(verbose, f"Did not find TOML-file at {tomlfile_path}")
        toml_config = dict()

    # Get the checkout directory where the snapshot will be rebuilt
    name: Optional[str] = config.get("name")
    if name is None:
        raise ValueError(f"'name' not found in {lockfile_path.name}")
    # If a destination has been supplied, use it. Otherwise default to '~/.ugle/'
    if destination_path_str is not None:
        checkout_dir = Path(destination_path_str).expanduser().resolve()
    else:
        checkout_dir = (Path("~/.ugle/") / name).expanduser().resolve()

    # Create the checkout directory
    # If 'force' is supplied, it will overwrite necessary files
    if checkout_dir.exists() and force:
        shutil.rmtree(checkout_dir)
    checkout_dir.mkdir(parents=True)  # Will raise an error if the folder exists

    verbose_print(verbose, "-" * 10)

    # Commands to run when checking out the snapshot
    commands: dict[str, list[list[str]]] = dict()

    deps = config.get("deps")
    if deps is not None:
        load_deps(deps, toml_config, checkout_dir, commands, verbose)

    # Run all the accumulated commands
    print()
    print("=" * 10)
    for dir, dep_cmds in commands.items():
        verbose_print(verbose, "-" * 5)
        # Make sure the directory exists
        Path(dir).mkdir(parents=True)
        print(f"In: {dir}")
        for cmd in dep_cmds:
            verbose_print(verbose, "Running: " + " ".join(cmd))
            output = subprocess.run(cmd, capture_output=True, cwd=dir)
            err = output.returncode
            # If errors occured, print them and raise en exception
            if err != 0:
                print(f"Error encountered in {dir} when running \n$ {" ".join(cmd)}")
                raise Exception(err)
    print("=" * 10)
    print()

    verbose_print(verbose, f"Checking for Spack dependencies")
    spack_config = config.get("spack")
    # If there is a Spack env
    if spack_config is not None:
        spack_file = checkout_dir / "spack.lock"
        # If the spack file already exists, we need to overwrite it to avoid
        # getting the system into a limbo where nothing in the folder works.
        if spack_file.exists():
            verbose_print(verbose, f"Removing old spack.lock: {spack_file}")
            os.remove(spack_file)

        verbose_print(verbose, f"Dumping Spack lockfile into {spack_file}")
        # Create lockfile and dump the lockfile contents into it
        with open(spack_file, "w") as f:
            json.dump(spack_config, f)

        # Notify of Spack environement
        print()
        print("#" * 60)
        print("To create and activate the spack environment:")
        print("#" * 60)
        print(f"$ cd {spack_file.parent}")
        print(f"$ spack env create <name> {spack_file.name}")
        print(f"$ spack env activate <name>")
        print("$ spack install")


def load_deps(
    deps: dict[str, dict[str, str]],
    toml_config: dict,
    checkout_dir: Path,
    commands: dict[str, list[list[str]]],
    verbose: bool = False,
):
    """Checkout local dependencies not installed by Spack

    ---
    Args:
        deps : `dict[str, dict[str, str]]`
            The local dependencies to take snapshot of. Structured as
            { <dep-name>: { "filepath": <filepath>, "url": <url>, ... }, ... }

        toml_config : `dict`
            Additional configuration supplied by the TOML-file. Is used in
            case dependencies have been moved since the snapshot was created.

        checkout_dir : `Path`
            The directory where the snapshot will be recreated at.

        commands : `dict[str, list[list[str]]]`
            Commands to run when recreating the snapshot.
            They are supplied to `subprocess.run()`. Structured as
            {
                <filepath_to_run_cmd_from>: [
                    [<cmd>],
                    [<cmd>],
                    ...
                ],
                <filepath_to_run_cmd_from>: [
                    [<cmd>],
                    [<cmd>],
                    ...
                ],
                ...
            }
            The commands are run in order from top to bottom at the specified filepath

        verbose : `bool`, default=False
            Enable verbose printing

    ---
    Returns:
        None
    """
    for dep_name, dep in deps.items():
        lock_filepath = Path(dep["filepath"])
        commit_hash = dep["hash"]
        url = dep.get("url")

        # If the dep exist in the TOML file, retrieve the filepath
        toml_deps = toml_config.get("deps")
        toml_filepath = None
        if toml_deps is not None:
            toml_dep = toml_deps.get(dep_name)
            if toml_dep is not None:
                toml_filepath = Path(toml_dep.get("filepath")).expanduser().resolve()

        # Load the dependency
        load_dep(
            dep_name,
            lock_filepath,
            toml_filepath,
            commit_hash,
            url,
            checkout_dir,
            commands,
            verbose,
        )


def load_dep(
    dep_name: str,
    lockfile_path: Path,
    tomlfile_path: Optional[Path],
    commit_hash: str,
    url: Optional[str],
    checkout_dir: Path,
    commands: dict[str, list[list[str]]],
    verbose: bool = False,
):
    """
    Checkout local dependency not installed by Spack.
    Assumes that the checkout_dir does not have a direct subfolder named `dep_name`

    ---
    Args:
        dep_name : `str`
            Name of the dependency to load

        lockfile_path : `Path`
            Filepath to dependency given by the lock-file

        tomlfile_path : `Optional[Path]`
            Filepath to dependency given by the TOML-file

        commit_hash : `str`
            The commit hash of the commit to checkout

        url : `Optional[str]`
            Git url of the dependency. If the repo with the specified
            commit is not found locally, the repo will be cloned from the supplied url

        checkout_dir : `Path`
            The directory where the snapshot will be recreated at.

        commands : `dict[str, list[list[str]]]`
            Commands to run when recreating the snapshot.
            They are supplied to `subprocess.run()`. Structured as
            {
                <filepath_to_run_cmd_from>: [
                    [<cmd>],
                    [<cmd>],
                    ...
                ],
                <filepath_to_run_cmd_from>: [
                    [<cmd>],
                    [<cmd>],
                    ...
                ],
                ...
            }
            The commands are run in order from top to bottom at the specified filepath

        verbose : `bool`, default=False
            Enable verbose printing

    ---
    Returns:
        None
    """
    # Paths to check for the commit. The last one is the default location to
    # clone in the git repo if the other two fails. Expects destination_path to
    # be empty
    destination_path = checkout_dir / dep_name
    destination_path_str = str(destination_path)
    src = None
    commands[destination_path_str] = []

    # If the `destination_path` exists, throw an error
    if destination_path.exists():
        raise FileExistsError(f"{destination_path} already exists. Can not continue")

    verbose_print(verbose, f"Looking for commit: {commit_hash}")

    # If we did not find the commit there already, we need to search more
    # directories
    if src is None:
        search_paths = [lockfile_path, tomlfile_path]

        for path in search_paths:
            verbose_print(verbose, f"Looking in {path}")

            # If the path does not exist, move on to the next
            if path is None or not path.exists():
                continue
            if commit_exists(path, commit_hash):
                # If the commit exists at the filepath location, break
                verbose_print(verbose, f"Found commit in: {path}")
                src = path
                commands[destination_path_str].append(
                    ["cp", "-r", str(path), str(destination_path.parent)]
                )
                break

        if src is None and url is not None:
            # Want to clone the repo to see if it has the commit.

            # Clone the repo
            verbose_print(verbose, f"Cloning from {url} into {destination_path}")
            subprocess.run(["git", "clone", url, destination_path])

            if commit_exists(destination_path, commit_hash):
                # If the commit exists, move it to the destination directory
                verbose_print(verbose, f"Commit found at {url}.")
                src = destination_path
            else:
                # If the commit does not exist, remove the pulled repo
                verbose_print(
                    verbose, f"Commit not found at {destination_path}. Cleaning up"
                )
                shutil.rmtree(destination_path)

    if src is None:
        # TODO: Improve error msg
        raise Exception("The commit could not be found")

    # Get 'git status' but ignoring untracked files
    git_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        cwd=src,
    ).stdout.decode()
    if not git_status == "":
        # Remove all non-committed changes and untracked files
        # from destination_path (not src)
        commands[destination_path_str].append(["git", "reset", "--hard", "HEAD"])

        # TODO: Figure out if we want to remove untracked files as well. Should
        # change the 'if not git_status == ""' as well

        # commands[destination_path_str].append(["git", "clean", "-dfx"])

    commands[destination_path_str].append(["git", "checkout", commit_hash])

    verbose_print(verbose, "-" * 10)


def commit_exists(path: Path, commit_hash: str) -> bool:
    """Check if the commit exists in a Git repo at the given filepath

    ---
    Args:
        path : `Path`
            The directory to search for the commit hash.

        commit_hash : `str`
            The commit hash of the commit to checkout
    ---
    Returns:
        `bool`
        True if the commit exists, False otherwise
    """
    # Get cwd, so we can return to it after the function has executed
    if (
        subprocess.run(
            ["git", "cat-file", "commit", commit_hash], capture_output=True, cwd=path
        ).stderr.decode()
        == ""
    ):
        return True
    return False
