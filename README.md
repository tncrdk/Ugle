# Ugle <sub><sup>*[u`glə]*</sup></sub>
Prototype of a program meant to create snapshots of multiple git repos scattered
across the filesystem and dependencies installed with `Spack`.

## How does it work?
Creating a snapshot with `Ugle` works by reading a supplied `.toml`-file
which defines which dependencies to take a snapshot of.
The exact git commit hashes for all dependencies are then stored in
`.lock`-file together with the contents of a `spack.lock`-file if a
spack environment is being used.
This requires all
dependencies to be git repos, not necessarily public ones, to be able to
snapshot them.
The `.lock`-file created bears the same name as the supplied `.toml`-file.

Restoring a snapshot with `Ugle` creates a copy of all the dependencies,
checked out to the correct commit, stored under a
common folder, by default `~/.ugle/<name>`.
The spack.lock file is also
recreated, which can be used to recover the spack environment.

If one or more of the original git repos can not be found at the
corresponding filepath
stored in the `.lock`-file, `Ugle` looks in the corresponding `.toml`-file,
if it exists, for other potential filepaths to search for the missing repo in.
If this also fails, `Ugle` will check if a url to a remote git repo is supplied in the
`.lock`-file. If not, the program exits with an error.
If on the other hand the url exists, it
will try to clone the repo and see if the commit hash exists here. If it
exists, `Ugle` will use it when recreating the snapshot, and if not it will exit
with an error.
For this reason, if the repo is stored in a remote repo it is recommended to
supply the url to make the snapshot more robust.

## Installation
*WIP*

Clone the repo and add `main.py` to PATH.
