import argparse
import subprocess
import tomllib
import shutil
import os
from pathlib import Path


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

    # If there is a Spack entry, handle it
    spack_config = config.get("spack")
    if spack_config is not None:
        spack_deps(spack_config, snapshot, work_dir, toml_file_path)

    # Other dependencies
    deps = config.get("deps")
    if deps is not None:
        handle_other_deps(deps, snapshot, work_dir)

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
    for dep_name, dep in deps.items():
        filepath = dep.get("filepath")
        url = dep.get("url")
        if filepath is not None and url is not None:
            # Choose if want github or local version
            print(
                f"Both a local path and an url has been supplied. Which one should the snapshot be based on?"
            )
            while True:
                ans = input("[0=url, 1=filepath]: ").strip()
                if ans == "0":
                    github_deps(dep_name, url, snapshot, work_dir)
                    break
                elif ans == "1":
                    local_deps(dep_name, filepath, snapshot, work_dir)
                    break
        elif filepath is not None:
            local_deps(dep_name, filepath, snapshot, work_dir)
        elif url is not None:
            github_deps(dep_name, url, snapshot, work_dir)
        else:
            raise ValueError(
                f"The dependency {dep_name} does not supply neither a filepath or an url."
            )


def local_deps(name: str, filepath_str: str, snapshot: dict, work_dir: Path):
    filepath = create_absolute_path(Path(filepath_str), work_dir)
    os.chdir(filepath)
    git_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True)
    if not git_status == "":
        print(f"The working tree of {filepath} is not clean.")
        print(git_status)
        while True:
            print(
                "Do you want to continue creating a snapshot? Note that only committed changes will be added to the snapshot."
            )
            ans = input("[y/n]: ").strip()
            if ans == "y":
                break
            elif ans == "n":
                raise Exception("Procedure cancelled")
    commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True)
    snapshot["deps"]["dep_name"] = {
        "filepath": filepath,
        "hash": commit_hash,
    }


def github_deps(name: str, url: str, snapshot: dict, work_dir: Path):
    pass


def main():
    parser = argparse.ArgumentParser("Ugle", description="Create and retrieve snapshot")
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
    print(args.work_dir)
    snapshot(args.work_dir)
    # args.func(args)


if __name__ == "__main__":
    main()
