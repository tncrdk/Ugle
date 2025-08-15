import json
import tomllib
import shutil
import os
import subprocess
from pathlib import Path
from typing import Optional

from utils import (
    check_tool_existence,
    verbose_print,
    check_if_file_exists,
    check_subprocess_error,
)


# ====================================================================================
# Checkout
# ====================================================================================


def checkout(
    zipfile_path_str: str,
    destination_path_str: str | None,
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
        zipfile_path_str : `str`
            The filepath to the zipfile we will load the snapshot from

        destination_path_str : `Optional[str]`
            Alternative destination to recreate the snapshot. If not supplied, the snapshot will be created at `~/.ugle/`

        force : `bool`, default=False
            If force is supplied, necessary files and folders will be overwritten for the checkout to succeed

        verbose : `bool`, default=False
            Enable verbose printing

    ---
    Returns:
        None
    """
    # Check if the dependencies of the script are available on the system
    check_script_dependencies()

    print()
    print("UNZIP")
    zipfile_path = Path(zipfile_path_str).expanduser().resolve()
    # Check if the zipfile exists
    verbose_print(verbose, f"Looking for zipfile at '{zipfile_path}'")
    exists, err_msg = check_if_file_exists(zipfile_path)
    if not exists:
        raise FileNotFoundError(err_msg)
    verbose_print(verbose, f"Found zipfile at '{zipfile_path}'")

    # Get the checkout directory where the snapshot will be rebuilt
    name = zipfile_path.stem
    # If a destination has been supplied, use it. Otherwise default to '~/.ugle/'
    if destination_path_str is not None:
        checkout_dir = Path(destination_path_str).expanduser().resolve()
    else:
        checkout_dir = (Path("~/.ugle/") / name).expanduser().resolve()

    # Create the checkout directory
    # If 'force' is supplied, it will overwrite necessary files
    if checkout_dir.exists():
        if force:
            shutil.rmtree(checkout_dir)
        else:
            raise ValueError(f"'{checkout_dir}' already exists. Aborting")

    # Surround the following in a try-block so we can clean up in case an error
    # is thrown
    try:
        # Unpack the zipfile
        print(f"Unzipping '{zipfile_path}' into '{checkout_dir}'")
        shutil.unpack_archive(zipfile_path, extract_dir=checkout_dir)

        # Resolve the lockfile path
        lockfile_path = checkout_dir / "ugle.lock"

        # Check if the lockfile exists
        verbose_print(verbose, "")
        verbose_print(verbose, f"Looking for lockfile at '{lockfile_path}'")
        exists, err_msg = check_if_file_exists(lockfile_path)
        if not exists:
            raise FileNotFoundError(err_msg)

        # If found, open the lockfile
        verbose_print(verbose, f"Found lockfile at '{lockfile_path}'\n")
        with open(lockfile_path, "r") as f:
            config = json.load(f)

        # Create TOML filepath based on the lockfile
        tomlfile_path = lockfile_path.with_suffix(".toml")

        # Check if the TOML file exists
        verbose_print(verbose, f"Looking for TOML-file at '{tomlfile_path}'")
        exists, err_msg = check_if_file_exists(tomlfile_path)
        if exists:
            # Open the TOML file if it exists
            verbose_print(verbose, f"Found TOML-file at '{tomlfile_path}'")
            with open(tomlfile_path, "rb") as f:
                toml_config = tomllib.load(f)
        else:
            # Default to empty dict if the TOML file does not exist
            verbose_print(verbose, f"Did not find TOML-file at '{tomlfile_path}'")
            toml_config = dict()

        deps = config.get("deps")
        if deps is not None:
            print()
            print("=" * 20)
            print()
            print("DEPENDENCIES (GIT)")
            load_deps(deps, toml_config, checkout_dir, verbose)

        # Create necessary dockerfiles
        create_dockerfiles(config, checkout_dir, verbose)

        print("-" * 20)
        print("SPACK")
        verbose_print(verbose, f"Checking for Spack dependencies")
        spack_config = config.get("spack")
        # If there is a Spack env
        if spack_config is not None:
            spack_file = checkout_dir / "spack.lock"
            # The spackfile should not exist.
            if spack_file.exists():
                verbose_print(verbose, f"Removing old spack.lock: {spack_file}")
                os.remove(spack_file)

            print(f"Dumping Spack lockfile into '{spack_file}'")
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

        # Print instructions for Docker
        print()
        print("#" * 60)
        print("To run the Docker-container:")
        print("#" * 60)
        print(f"$ cd {checkout_dir}")
        print(f"$ docker build . -t <image name>")
        print(f"[ Update docker-compose.yaml with the correct names ]")
        print(f"$ docker compose up -d")
        print("$ docker compose exec <service name> bash")

    except Exception as err:
        # If something fails, clean up
        shutil.rmtree(checkout_dir)
        # Propagate the error
        raise err


def load_deps(
    deps: dict[str, dict[str, str]],
    toml_config: dict,
    checkout_dir: Path,
    verbose: bool = False,
):
    """Checkout local dependencies not installed by package managers

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

        verbose : `bool`, default=False
            Enable verbose printing

    ---
    Returns:
        None
    """
    for dep_name, dep in deps.items():
        copy = dep.get("copy")
        # If the dep was copied, it is already handled by unpacking the zipfile
        if copy:
            continue

        lock_filepath = Path(dep["filepath"])
        commit_hash = dep["hash"]
        url = dep.get("url")

        # If the dep exist in the TOML file, retrieve the filepath
        toml_filepath = None
        toml_deps = toml_config.get("deps")
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
            verbose,
        )


def load_dep(
    dep_name: str,
    lockfile_path: Path,
    tomlfile_path: Optional[Path],
    commit_hash: str,
    url: Optional[str],
    checkout_dir: Path,
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

        verbose : `bool`, default=False
            Enable verbose printing

    ---
    Returns:
        None
    """
    verbose_print(verbose, "-" * 10)
    print(f"Checkout of {dep_name}")
    # Paths to check for the commit. The last one is the default location to
    # clone in the git repo if the other two fails. Expects destination_path to
    # be empty

    destination_path = checkout_dir / dep_name
    src = None

    # If the `destination_path` exists, throw an error
    if destination_path.exists():
        raise FileExistsError(f"{destination_path} already exists. Can not continue")

    verbose_print(verbose, f"Looking for commit: {commit_hash}")

    # Possible search paths to investigate when looking for dependency
    search_paths = [lockfile_path, tomlfile_path]
    for path in search_paths:
        verbose_print(verbose, f"Looking in: {path}")

        # If the path does not exist, move on to the next
        if path is None or not path.exists():
            continue
        if commit_exists(path, commit_hash):
            # If the commit exists at the filepath location, copy the files and break
            verbose_print(verbose, f"Found commit in: {path}")
            src = path
            output = subprocess.run(
                ["cp", "-r", str(path), str(destination_path.parent)],
                capture_output=True,
            )
            check_subprocess_error(output)
            break

    # In case we have not found the commit yet, clone the remote repo if it
    # exists
    if src is None and url is not None:
        # Want to clone the repo to see if it has the commit.

        # Clone the repo
        verbose_print(verbose, f"Cloning from {url} into {destination_path}")
        output = subprocess.run(
            ["git", "clone", url, destination_path], capture_output=True
        )
        check_subprocess_error(output)

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
        raise Exception(
            f"The commit, {commit_hash}, could not be found for the dependency {dep_name}"
        )

    # Get 'git status' but ignoring untracked files
    git_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        cwd=destination_path,
    ).stdout.decode()
    if not git_status == "":
        # Remove all non-committed changes
        # from destination_path (not src) so that we can checkout
        verbose_print(verbose, f"Running: git reset --hard HEAD")
        output = subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            capture_output=True,
            cwd=destination_path,
        )
        check_subprocess_error(output, destination_path)

        # TODO: Figure out if we want to remove untracked files as well. Should
        # change the 'if not git_status == ""' as well

        # commands[destination_path_str].append(["git", "clean", "-dfx"])

    verbose_print(verbose, f"Running: git checkout {commit_hash}")
    output = subprocess.run(
        ["git", "checkout", commit_hash],
        cwd=destination_path,
        capture_output=True,
    )
    check_subprocess_error(output, destination_path)


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
    # If the following command throws an error, then the commit does not exist
    if (
        subprocess.run(
            ["git", "cat-file", "commit", commit_hash], capture_output=True, cwd=path
        ).stderr.decode()
        == ""
    ):
        return True
    return False


def create_dockerfiles(snapshot: dict, checkout_dir: Path, verbose: bool = False):
    print()
    print("=" * 20)
    print()
    print("DOCKER")
    # Create the path to the local exports folder
    local_exports_path = Path(__file__).parent / "exports"

    # Get head and tail of Dockerfile
    # (Everything except the volume-declarations)
    with open(local_exports_path / "Dockerfile-head.txt", "r") as f:
        docker_head = f.read()
    with open(local_exports_path / "Dockerfile-tail.txt", "r") as f:
        docker_tail = f.read()
    # Get docker-compose
    with open(local_exports_path / "docker-compose.yaml", "r") as f:
        docker_compose = f.read()

    deps = snapshot.get("deps")
    if deps is None:
        # If there are no deps, concatenate head and tail
        verbose_print(verbose, "No Apt dependencies.")
        dockerfile = docker_head + docker_tail
        # If there are not deps, we don't need docker-compose
    else:
        verbose_print(verbose, f"Adding Apt dependencies")
        volume_declaration = []
        compose_declaration = ["    volumes:"]

        # Get the filepaths of the dependencies
        for dep_name in deps.keys():
            path = checkout_dir / Path(dep_name)

            volume_declaration.append(f"VOLUME /home/Code/{path.name}")
            # Tab-indent: 6 spaces
            compose_declaration.append(f"      - {path}:/home/Code/{path.name}")

        dockerfile = docker_head + "\n".join(volume_declaration) + docker_tail
        docker_compose = docker_compose + "\n".join(compose_declaration)

    # Write Dockerfile
    print("Writing Dockerfile")
    with open(checkout_dir / "Dockerfile", "w") as f:
        f.write(dockerfile)

    # Write docker-compose file
    print("Writing docker-compose.yaml")
    with open(checkout_dir / "docker-compose.yaml", "w") as f:
        f.write(docker_compose)


def check_script_dependencies():
    check_tool_existence("git")
    check_tool_existence("dpkg-repack")
    check_tool_existence("apt-cache")
    check_tool_existence("cp")
