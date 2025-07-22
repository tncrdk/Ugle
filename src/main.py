import argparse
import subprocess
import tomllib
import json
import shutil
import os
from pathlib import Path
from typing import Optional


# TODO: Snapshot of python packages -> Conclusion: People needs to create a
# venv, Pipfile.lock, etc and version control these files in order to snapshot
# the python packages.

# TODO: Snapshot of javascript packages -> Conclusion: use npm-lock.json

# TODO: Snapshot which spack repos packages are coming from?


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
    if not path.is_absolute():
        return (work_dir / path).resolve()
    return path


# ====================================================================================
# Snapshot
# ====================================================================================


def snapshot(work_dir_str: str):
    snapshot = dict()
    work_dir = Path(work_dir_str).resolve()
    # Copy spack lock file (if exists)
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

    # TODO: Handle current folder project

    # If there is a Spack entry, handle it
    spack_config = config.get("spack")
    if spack_config is not None:
        spack_deps(spack_config, snapshot, work_dir, toml_file_path)

    # Other dependencies
    deps = config.get("deps")
    if deps is None:
        deps = {"work_dir": {"filepath": "."}}
    else:
        deps["work_dir"] = {"filepath": "."}

    handle_other_deps(deps, snapshot, work_dir)

    with open("ugle.lock", "w") as f:
        json.dump(snapshot, f)

    print("DONE!")


def spack_deps(
    spack_config: dict[str, str], snapshot: dict, work_dir: Path, toml_file_path: Path
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
    exists, err_msg = check_if_file_exists(lockfile_path)
    if not exists:
        raise ValueError(err_msg)
    # lockfile is now guaranteed to be a file
    if lockfile_path.parent != work_dir:
        # Copy the spack file to the working directory
        shutil.copy(lockfile_path, work_dir / lockfile_path.name)

    # Store the location of the lock-file
    snapshot["spack"] = str(work_dir / lockfile_path.name)


def handle_other_deps(deps: dict[str, dict[str, str]], snapshot: dict, work_dir: Path):
    # deps structure:
    # deps = { <dep-name>: {filepath: <file>, url: <url>}, <dep-2>: {filepath: <file>, url: <url>}}
    snapshot["deps"] = dict()
    for dep_name, dep in deps.items():
        filepath = dep.get("filepath")
        # TODO: Get url from 'git remote -v'
        url = dep.get("url")
        if filepath is not None:
            local_deps(dep_name, filepath, snapshot, work_dir, url)
        else:
            raise ValueError(
                f"The dependency {dep_name} does not supply a filepath nor an url."
            )


def local_deps(
    name: str, filepath_str: str, snapshot: dict, work_dir: Path, url: Optional[str]
):
    """
    Expected to be a local git repo
    """
    filepath = create_absolute_path(Path(filepath_str), work_dir)
    os.chdir(filepath)
    git_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True)
    # If something goes wrong with the above command, it needs to be fixed
    if not git_status.returncode == 0:
        # TODO: Create better exception type and error message. Ex: which dep
        # gave the error
        raise Exception(git_status.stderr.decode())
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
    # Get the commit-hash of the commit currently being check out
    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True
    ).stdout.decode()
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


def checkout(work_dir_str: str):
    work_dir = Path(work_dir_str).resolve()
    # Copy spack lock file (if exists)
    # store commit hash and either url or filepath to all other deps

    # Check existence
    if not work_dir.exists():
        raise ValueError(f"{work_dir} does not exist")
    lock_file_path = work_dir / "ugle.lock"
    exists, err_msg = check_if_file_exists(lock_file_path)
    if not exists:
        raise ValueError(err_msg)

    with open(lock_file_path, "r") as f:
        config = json.load(f)

    # Commands to run when checking out the snapshot
    commands = []

    deps = config.get("deps")
    if deps is not None:
        load_deps(deps, work_dir, commands)

    spack_config = config.get("spack")
    if spack_config is not None:
        print("To create and activate the spack environment:")
        print(f"spack env create <name> {spack_config}")


def load_deps(
    deps: dict[str, dict[str, str]], work_dir: Path, commands: list[list[str]]
):
    for dep_name, dep in deps.items():
        filepath = dep.get("filepath")
        commit_hash = dep.get("hash")
        url = dep.get("url")
        pass


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
    snapshot(args.work_dir)
    # args.func(args)


if __name__ == "__main__":
    main()
