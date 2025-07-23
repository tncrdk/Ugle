import argparse
import subprocess
import tomllib
import json
import shutil
import os
import uuid
from pathlib import Path
from typing import Optional


# TODO: Snapshot of python packages -> Conclusion: People needs to create a
# venv, Pipfile.lock, etc and version control these files in order to snapshot
# the python packages.

# TODO: Snapshot of javascript packages -> Conclusion: use npm-lock.json

# TODO: Snapshot which spack repos packages are coming from?

# TODO: Improve error handling

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
        # deps = {"work_dir": {"filepath": "."}}
        deps = dict()
    # else:
    #     deps["work_dir"] = {"filepath": "."}

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
    print(lockfile_path)
    # Resolves the path to an absolute path
    lockfile_path = create_absolute_path(lockfile_path, work_dir)
    print(lockfile_path)
    exists, err_msg = check_if_file_exists(lockfile_path)
    if not exists:
        raise ValueError(err_msg)
    # lockfile is now guaranteed to be a file
    if lockfile_path.parent != work_dir:
        # Copy the spack file to the working directory
        shutil.copy(lockfile_path, work_dir / lockfile_path.name)

    # TODO: Consider copying contents of lock file into the snapshot-dict

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
    toml_file_path = work_dir / "ugle.toml"
    exists, err_msg = check_if_file_exists(lock_file_path)

    # Check if the lock file exists
    if not exists:
        raise ValueError(err_msg)
    # Open the lock file
    with open(lock_file_path, "r") as f:
        config = json.load(f)

    # Check if the TOML file exists
    exists, err_msg = check_if_file_exists(toml_file_path)
    if not exists:
        # Default to empty dict if the TOML file does not exist
        toml_config = dict()
    else:
        with open(toml_file_path, "rb") as f:
            toml_config = tomllib.load(f)

    # Commands to run when checking out the snapshot
    commands: dict[str, list[list[str]]] = dict()

    deps = config.get("deps")
    if deps is not None:
        load_deps(deps, toml_config, work_dir, commands)

    # Run all the accumulated commands
    print("=" * 10)
    for dep_cmds in commands.values():
        print("-" * 5)
        for cmd in dep_cmds:
            print("Running: ", " ".join(cmd))
            output = subprocess.run(cmd, capture_output=True)
            err = output.stderr.decode()
            if err != "":
                print("Error: ", err)
            print("Finished: ", " ".join(cmd))
    print("=" * 10)

    # Notify of Spack environement
    spack_config = config.get("spack")
    if spack_config is not None:
        print("To create and activate the spack environment:")
        print(f"spack env create <name> {spack_config}")
        print(f"spack env activate <name>")


def load_deps(
    deps: dict[str, dict[str, str]],
    toml_config: dict,
    work_dir: Path,
    commands: dict[str, list[list[str]]],
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
                toml_filepath = Path(toml_dep.get("filepath"))

        # Paths to check for the commit. The last one is the default location to
        # clone in the git repo if the other two fails.
        clone_path = work_dir / ".." / dep_name
        paths = [lock_filepath, toml_filepath, clone_path]
        src = None
        for path in paths:
            # If the path does not exist, move on to the next
            if path is None or not path.exists():
                continue
            os.chdir(path.parent)
            if commit_exists(commit_hash):
                # If the commit does not exist at the filepath location, move on
                continue
            else:
                src = path

        if src is None and url is not None:
            # Want to clone the repo into a default location.
            # If the folder exists, create a new folder with the same name but
            # with a random sequence of numbers at the end
            if clone_path.exists():
                random_uuid = uuid.uuid4()
                clone_path = Path(str(clone_path) + "-" + str(random_uuid))
            # Clone the repo
            subprocess.run(
                ["git", "clone", url, clone_path.resolve().absolute()],
                capture_output=True,
            )
            # Navigate to the cloned repo
            os.chdir(clone_path)

            # If the commit does not exist here either, return error
            if commit_exists(commit_hash):
                # If the commit does not exist at the filepath location, go to
                # github if the url exists. If not abort
                # TODO: Improve error msg
                raise Exception("Commit can not be found at filepath")
            # Else the cloned repo is the src
            src = clone_path
        elif src is None:
            # TODO: Improve error msg
            raise Exception("The commit could not be found")

        # The absolute path to be used as key in commands dict
        path_key = str(src.absolute())
        # Init commands for this dep
        commands[path_key] = []

        git_status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True
        ).stdout.decode()
        if not git_status == "":
            while True:
                print("The working tree is not empty. Do you want to abort?")
                print("Note that all changes will be stashed if not aborted.")
                ans = input("[y/n]: ").strip()
                if ans == "n":
                    break
                if ans == "y":
                    raise Exception("Aborted")
                print("Invalid input. Try again\n")
            # If yes, run git stash before checking out
            commands[path_key].append(["git", "stash", "push", "-m", "Ugle stash. Automatic"])

        commands[path_key].append(["git", "checkout", commit_hash])


def commit_exists(commit_hash: str) -> bool:
    if (
        subprocess.run(
            ["git", "cat-file", "commit", commit_hash], capture_output=True
        ).stderr.decode()
        == ""
    ):
        return True
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
    snapshot(args.work_dir)
    # checkout(args.work_dir)
    # args.func(args)


if __name__ == "__main__":
    main()
