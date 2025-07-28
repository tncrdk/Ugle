import json
import tomllib
import shutil
import os
import subprocess
from pathlib import Path
from typing import Optional

import utils


# ====================================================================================
# Checkout
# ====================================================================================


def checkout(work_dir_str: str, verbose: bool = False):
    # Copy spack lockfile (if exists)
    # store commit hash and either url or filepath to all other deps

    # Get the working directory for the snapshot
    work_dir = Path(work_dir_str).resolve()

    # Check existence
    if not work_dir.exists():
        raise FileNotFoundError(f"{work_dir} does not exist")

    # Create lockfile and TOML filepaths
    lockfile_path = work_dir / "ugle.lock"
    tomlfile_path = work_dir / "ugle.toml"

    utils.verbose_print(verbose, f"Looking for lockfile at {lockfile_path}")
    # Check if the lockfile exists
    exists, err_msg = utils.check_if_file_exists(lockfile_path)
    if not exists:
        raise FileNotFoundError(err_msg)
    utils.verbose_print(verbose, f"Found lockfile at {lockfile_path}")
    # Open the lockfile
    with open(lockfile_path, "r") as f:
        config = json.load(f)

    # Create the checkout directory where the snapshot will be rebuilt
    name: Optional[str] = config.get("name")
    if name is None:
        raise ValueError("'name' not found")
    checkout_dir = (Path("~/.ugle/") / name).expanduser().resolve().absolute()

    utils.verbose_print(verbose, f"Looking for TOML-file at {tomlfile_path}")
    # Check if the TOML file exists
    exists, err_msg = utils.check_if_file_exists(tomlfile_path)
    if exists:
        utils.verbose_print(verbose, f"Found TOML-file at {tomlfile_path}")
        # Open the TOML file if it exists
        with open(tomlfile_path, "rb") as f:
            toml_config = tomllib.load(f)
    else:
        utils.verbose_print(verbose, f"Did not find TOML-file at {tomlfile_path}")
        # Default to empty dict if the TOML file does not exist
        toml_config = dict()

    utils.verbose_print(verbose, "-" * 10)

    # Commands to run when checking out the snapshot
    commands: dict[str, list[list[str]]] = dict()

    deps = config.get("deps")
    if deps is not None:
        load_deps(deps, toml_config, work_dir, checkout_dir, commands, verbose)

    # Make sure the snapshot directory exists
    checkout_dir.mkdir(parents=True, exist_ok=True)

    # Run all the accumulated commands
    print()
    print("=" * 10)
    for dir, dep_cmds in commands.items():
        print("-" * 5)
        # Make sure the directory exists
        Path(dir).mkdir(parents=True, exist_ok=True)
        os.chdir(dir)
        print(f"In: {dir}")
        for cmd in dep_cmds:
            print("Running: ", " ".join(cmd))
            output = subprocess.run(cmd, capture_output=True)
            err = output.returncode
            # If errors occured, print them
            if err != 0:
                print("Error: ", err)
    print("=" * 10)
    print()

    utils.verbose_print(verbose, f"Checking for Spack dependencies")
    spack_config = config.get("spack")
    # If there is a Spack env
    if spack_config is not None:
        spack_file = checkout_dir / Path("spack.lock")
        # Check that we are not overwriting any files when creating the
        # spack.lock file. If we are, append a uuid at the end.
        if spack_file.exists():
            utils.verbose_print(verbose, f"Removing old spack.lock: {spack_file}")
            os.remove(spack_file)

        utils.verbose_print(verbose, f"Dumping Spack lockfile into {spack_file}")
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
    work_dir: Path,
    checkout_dir: Path,
    commands: dict[str, list[list[str]]],
    verbose: bool = False,
):
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
                toml_filepath = (
                    Path(toml_dep.get("filepath")).expanduser().resolve().absolute()
                )

        # Load the dependency
        load_dep(
            dep_name,
            lock_filepath,
            toml_filepath,
            commit_hash,
            url,
            work_dir,
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
    work_dir: Path,
    checkout_dir: Path,
    commands: dict[str, list[list[str]]],
    verbose: bool = False,
):
    # Paths to check for the commit. The last one is the default location to
    # clone in the git repo if the other two fails.
    destination_path = checkout_dir / dep_name
    destination_path_str = str(destination_path)
    src = None
    commands[destination_path_str] = []

    utils.verbose_print(verbose, f"Looking for commit: {commit_hash}")
    utils.verbose_print(verbose, f"Looking in {destination_path}")

    # If the directory already exists, check if commit can be found there
    if destination_path.exists():
        if commit_exists(destination_path, commit_hash):
            # If the commit exists here, we don't have to do anything
            utils.verbose_print(verbose, f"Found commit at {destination_path}")
            src = destination_path
        else:
            # If the commit can not be found, remove this directory
            utils.verbose_print(
                verbose, f"Commit not found. Will remove {destination_path}"
            )
            shutil.rmtree(destination_path)

    # If we did not find the commit there already, we need to search more
    # directories
    if src is None:
        search_paths = [lockfile_path, tomlfile_path]

        for path in search_paths:
            utils.verbose_print(verbose, f"Looking in {path}")

            # If the path does not exist, move on to the next
            if path is None or not path.exists():
                continue
            if commit_exists(path, commit_hash):
                # If the commit exists at the filepath location, break
                utils.verbose_print(verbose, f"Found commit in: {path}")
                src = path
                commands[destination_path_str].append(
                    ["cp", "-r", str(path), str(destination_path.parent)]
                )
                break

        if src is None and url is not None:
            # Want to clone the repo to see if it has the commit.

            # Clone the repo
            utils.verbose_print(verbose, f"Cloning from {url} into {destination_path}")
            subprocess.run(["git", "clone", url, destination_path])

            if commit_exists(destination_path, commit_hash):
                # If the commit exists, move it to the destination directory
                utils.verbose_print(verbose, f"Commit found at {url}.")
                found_commit = True
                src = destination_path
            else:
                # If the commit does not exist, remove the pulled repo
                utils.verbose_print(
                    verbose, f"Commit not found at {destination_path}. Cleaning up"
                )
                shutil.rmtree(destination_path)

    if src is None:
        # TODO: Improve error msg
        raise Exception("The commit could not be found")

    # Make sure we are in the source location
    os.chdir(src)

    # Get 'git status' but ignoring untracked files
    git_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True
    ).stdout.decode()
    if not git_status == "":
        # Remove all non-committed changes and untracked files
        # from destination_path (not src)
        commands[destination_path_str].append(["git", "reset", "--hard", "HEAD"])

        # TODO: Figure out if we want to remove untracked files as well. Should
        # change the 'if not git_status == ""' as well

        # commands[destination_path_str].append(["git", "clean", "-dfx"])

    commands[destination_path_str].append(["git", "checkout", commit_hash])

    # Change back to work_dir
    os.chdir(work_dir)

    utils.verbose_print(verbose, "-" * 10)


def commit_exists(path: Path, commit_hash: str) -> bool:
    cwd = os.getcwd()
    os.chdir(path)
    if (
        subprocess.run(
            ["git", "cat-file", "commit", commit_hash], capture_output=True
        ).stderr.decode()
        == ""
    ):
        os.chdir(cwd)
        return True

    os.chdir(cwd)
    return False
