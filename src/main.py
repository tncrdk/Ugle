#!/usr/bin/python3.12

import argparse
import subprocess
import tomllib
import json
import os
import uuid
import re
from pathlib import Path
from typing import Optional


# TODO: Snapshot of python packages -> Conclusion: People needs to create a
# venv, Pipfile.lock, etc and version control these files in order to snapshot
# the python packages.

# TODO: Snapshot of javascript packages -> Conclusion: use npm-lock.json

# TODO: Snapshot which spack repos packages are coming from?

# TODO: Improve error handling

# TODO: Add the date of the snapshot to the lockfile

# TODO: Consider instead of 'git checkout' the already existing repos, copy them
# into a predetermined folder, e.g. <name>-2024-03-21, and 'git checkout'
# there


# ====================================================================================
# Utils
# ====================================================================================


def check_if_file_exists(filename: Path) -> tuple[bool, str]:
    if not filename.exists():
        return (False, f"{filename.resolve()} does not exist.")
    if not filename.is_file():
        return (False, f"{filename.resolve()} is not a file.")
    return (True, "")


def create_absolute_path(path: Path, work_dir: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        return (work_dir / path).resolve()
    return path


# ====================================================================================
# Snapshot
# ====================================================================================


def snapshot(work_dir_str: str, verbose: bool = False):
    snapshot = dict()
    work_dir = Path(work_dir_str).resolve()
    # Copy spack lockfile (if exists)
    # store commit hash and either url or filepath to all other deps

    # Check existence
    if not work_dir.exists():
        raise ValueError(f"{work_dir} does not exist")
    toml_file_path = work_dir / "ugle.toml"
    exists, err_msg = check_if_file_exists(toml_file_path)
    if not exists:
        raise ValueError(err_msg)

    with open(toml_file_path, "rb") as f:
        config = tomllib.load(f)

    # Add the name of snapshot to the lockfile
    name = config.get("name")
    if name is None:
        raise Exception("Name is missing from ugle.toml")
    snapshot["name"] = name

    # If there is a Spack entry, handle it
    spack_config = config.get("spack")
    if spack_config is not None:
        spack_deps(spack_config, snapshot, work_dir, toml_file_path, verbose)

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
    toml_file_path: Path,
    verbose: bool = False,
):
    # This should exist
    lockfile_str = spack_config.get("lockfile")
    if lockfile_str is None:
        raise ValueError(
            f"spack has no attribute called 'lockfile' in {toml_file_path}."
        )
    lockfile_path = Path(lockfile_str)

    # Resolves the path to an absolute path
    lockfile_path = create_absolute_path(lockfile_path, work_dir)
    if verbose:
        print(f"Looking for spack lockfile in: {lockfile_path}")
    exists, err_msg = check_if_file_exists(lockfile_path)
    if not exists:
        raise ValueError(err_msg)

    if verbose:
        print(f"Loading contents of {lockfile_path}")
    # Extract the contents of the lockfile
    with open(lockfile_path, "r") as f:
        lockfile_content = json.load(f)

    if verbose:
        print(f"Storing contents of {lockfile_path} in snapshot")
    # Store the contents of the lockfile in the snapshot
    snapshot["spack"] = lockfile_content


def handle_other_deps(
    deps: dict[str, dict[str, str]],
    snapshot: dict,
    work_dir: Path,
    verbose: bool = False,
):
    # deps structure:
    # deps = { <dep-name>: {filepath: <file>, url: <url>}, <dep-2>: {filepath: <file>, url: <url>}}
    snapshot["deps"] = dict()
    for dep_name, dep in deps.items():
        filepath = dep.get("filepath")
        url = dep.get("url")

        if filepath is not None:
            local_dep(dep_name, filepath, snapshot, work_dir, url, verbose)
        else:
            raise ValueError(
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
    """
    Expected to be a local git repo
    """
    filepath = create_absolute_path(Path(filepath_str), work_dir)
    if verbose:
        print("=" * 10)
        print(f"Looking for {name} in {filepath}")
    if not filepath.exists():
        raise Exception(f"Filepath {filepath} does not exist")
    os.chdir(filepath)

    git_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True)
    # If something goes wrong with the above command, it needs to be fixed
    if not git_status.returncode == 0:
        # TODO: Create better exception type and error message. Ex: which dep
        # gave the error
        raise Exception(git_status.stderr.decode())

    if verbose:
        print("-" * 4)
        print("Checking the working tree")
    if not git_status.stdout.decode() == "":
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
                raise Exception("Snapshot aborted")
            print("Not valid")
    elif verbose:
        print("Working tree is clean")

    if verbose:
        print("-" * 4)
        print("Getting commit-hash")
    # Get the commit-hash of the commit currently being check out
    commit_hash = (
        subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True)
        .stdout.decode()
        .strip()
    )
    if verbose:
        print(f"Commit-hash: {commit_hash}")

    if verbose:
        print("-" * 4)
    # If url is not defined, try to get it from 'git remove -v'
    if url is None:
        if verbose:
            print("Trying to get url with 'git remote -v'")

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

            if verbose:
                print(f"Found url: {url}")
        elif verbose:
            print("Did not find url")
    elif verbose:
        print(f"url: {url}")

    if verbose:
        print(f"-" * 4)
        print(f"Adding {name} to snapshot")

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
        raise ValueError(f"{work_dir} does not exist")

    # Create lockfile and TOML filepaths
    lockfile_path = work_dir / "ugle.lock"
    tomlfile_path = work_dir / "ugle.toml"

    if verbose:
        print(f"Looking for lockfile at {lockfile_path}")
    # Check if the lockfile exists
    exists, err_msg = check_if_file_exists(lockfile_path)
    if not exists:
        raise ValueError(err_msg)
    # Open the lockfile
    with open(lockfile_path, "r") as f:
        config = json.load(f)

    if verbose:
        print(f"Looking for TOML-file at {tomlfile_path}")
    # Check if the TOML file exists
    exists, err_msg = check_if_file_exists(tomlfile_path)
    if exists:
        if verbose:
            print(f"Found TOML-file at {tomlfile_path}")
        # Open the TOML file if it exists
        with open(tomlfile_path, "rb") as f:
            toml_config = tomllib.load(f)
    else:
        if verbose:
            print(f"Did not find TOML-file at {tomlfile_path}")
        # Default to empty dict if the TOML file does not exist
        toml_config = dict()

    # Commands to run when checking out the snapshot
    commands: dict[str, list[list[str]]] = dict()

    deps = config.get("deps")
    if deps is not None:
        load_deps(deps, toml_config, work_dir, commands, verbose)

    # Run all the accumulated commands
    print()
    print("=" * 10)
    for dir, dep_cmds in commands.items():
        print("-" * 5)
        os.chdir(dir)
        print(f"In: {dir}")
        for cmd in dep_cmds:
            print("Running: ", " ".join(cmd))
            output = subprocess.run(cmd, capture_output=True)
            err = output.returncode
            # If errors occured, print them
            if err != 0:
                print("Error: ", err)
            print("Finished: ", " ".join(cmd))
    print("=" * 10)
    print()

    if verbose:
        print(f"Checking for Spack dependencies")
    spack_config = config.get("spack")
    # If there is a Spack env
    if spack_config is not None:
        spack_file = work_dir / Path("spack.lock")
        # Check that we are not overwriting any files when creating the
        # spack.lock file. If we are, append a uuid at the end.
        if spack_file.exists():
            while True:
                print(spack_file, " already exists.")
                print("Do you want to overwrite it?")
                res = input("[y/n]: ").strip()
                if res == "n":
                    random_uuid = uuid.uuid4()
                    spack_file = work_dir / Path(
                        str(spack_file.stem) + "-" + str(random_uuid) + ".lock"
                    )
                    break
                if res == "y":
                    break
                print("Invalid input")

        if verbose:
            print(f"Dumping Spack lockfile into {spack_file}")
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
    commands: dict[str, list[list[str]]],
    verbose: bool = False,
):
    # Paths to check for the commit. The last one is the default location to
    # clone in the git repo if the other two fails.
    clone_path = (work_dir / ".." / dep_name).resolve().absolute()
    paths = [lockfile_path, tomlfile_path, clone_path]
    src = None

    if verbose:
        print(f"Looking for commit: {commit_hash}")

    for path in paths:
        if verbose:
            print("Looking for commit in: ", path)

        # If the path does not exist, move on to the next
        if path is None or not path.exists():
            continue
        if commit_exists(path, commit_hash):
            # If the commit exists at the filepath location, break
            if verbose:
                print("Found commit in: ", path)
            src = path
            break

    if src is None and url is not None:
        # Want to clone the repo into a default location.
        # If the folder exists, create a new folder with the same name but
        # with a random sequence of numbers at the end
        if clone_path.exists():
            random_uuid = uuid.uuid4()
            clone_path = Path(str(clone_path) + "-" + str(random_uuid))

        if verbose:
            print(f"Cloning from {url} into {clone_path}")

        # Clone the repo
        subprocess.run(
            ["git", "clone", url, clone_path],
            capture_output=True,
        )
        # If the commit does not exist here either, return error
        if not commit_exists(clone_path, commit_hash):
            # TODO: Improve error msg
            raise Exception("Commit can not be found at filepath")
        # Else the cloned repo is the src
        src = clone_path

        if verbose:
            print("Found commit in: ", src)

    elif src is None:
        # TODO: Improve error msg
        raise Exception("The commit could not be found")

    # The absolute path to be used as key in commands dict
    path_key = str(src.resolve().absolute())
    # Init commands for this dep
    commands[path_key] = []

    # Make sure we are in the source location
    os.chdir(src)

    git_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True
    ).stdout.decode()
    if not git_status == "":
        while True:
            print(
                f"The working tree at {path_key} is not empty. Do you want to continue?"
            )
            print("Note that all changes will be stashed if not aborted.")
            ans = input("[y/n]: ").strip()
            if ans == "y":
                break
            if ans == "n":
                raise Exception("Aborted")
            print("Invalid input. Try again\n")
        # If yes, run git stash before checking out
        commands[path_key].append(
            ["git", "stash", "push", "-m", "Ugle stash. Automatic"]
        )

    commands[path_key].append(["git", "checkout", commit_hash])

    # Change back to work_dir
    os.chdir(work_dir)

    if verbose:
        print("-" * 10)


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


# ====================================================================================
# Program
# ====================================================================================


def main():
    parser = argparse.ArgumentParser("Ugle", description="Create and retrieve snapshot")
    # work_dir is the "root" of the snapshot.
    parser.add_argument("work_dir")
    # subparsers = parser.add_subparsers()
    # checkout_parser = subparsers.add_parser("checkout")
    # snapshot_parser = subparsers.add_parser("snapshot")
    #
    # checkout_parser.add_argument("work_dir")
    # checkout_parser.set_defaults(func=snapshot)
    # snapshot_parser.add_argument("home")
    # snapshot_parser.set_defaults(func=snapshot)

    args = parser.parse_args()
    # print(args.work_dir)
    snapshot(args.work_dir, verbose=True)
    # checkout(args.work_dir, verbose=True)
    # args.func(args)


if __name__ == "__main__":
    main()
