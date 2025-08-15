# Ugle <sub><sup>*[u`glə]*</sup></sub>
Prototype of a program meant to create snapshots of multiple git repos scattered
across the filesystem and dependencies installed with `Spack`.

## How does it work?
### Snapshotting
Creating a snapshot with `Ugle` works by reading a supplied `.toml`-file
which defines which dependencies to take a snapshot of.
Depending on whether the `copy` field is set to `true` or `false` for a given dependency,
the dependency is either copied as is into the snapshot,
or stored as a filepath and git commit hash in the
`.lock`-file. This of course requires the dependency to be a git repo.
If the repository has a remote as well, this will be recorded and
added to the `.lock`-file as well. 

If there is a `Spack` environment connected to the project, the `spack.lock` can
be added to the snapshot by specifying the `spack`-field in the `.toml`-file.
The `.lock`-file created shares the same name as the supplied `.toml`-file.

`apt`-packages can also be added by using the `apt`-field in `.toml`-file, where
a list of all the `apt`-dependencies is supplied.

Look at [example.toml](./ugle/example.toml) for an example.

The snapshot is lastly zipped into a zip-archive with name defined in the `.toml`-file
along with the date of the snapshot.

### Checkout
Restoring a snapshot with `Ugle` creates a copy of all the dependencies,
checked out to the correct commit, stored under a
common folder, by default `~/.ugle/<name>`.
The spack.lock file is also
recreated, which can be used to recover the spack environment.
Additionaly a `Dockerfile` and `docker-compose.yaml` will be created to handle
`apt`-packages.

If one or more of the original git repos can not be found at the
corresponding filepath
stored in the `.lock`-file, `Ugle` looks in the corresponding `.toml`-file,
if it exists, for other potential filepaths to search for the missing repo in.
If this also fails, `Ugle` will check if the commit exists at the in the repo at the url.
If either the url is not defined or the commit does not exist here, the program exits with an error.
Otherwise, it
will try to clone the repo into the snapshot location.

## Installation
Clone the repo locally and add only `main.py` to PATH.

**Example**
Clone the repo into a folder of your choice, then run the following:
```sh
mkdir -p ~/.local/bin/
cd ~/.local/bin/
ln -s $path-to-main.py ugle
```
