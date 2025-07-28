#!/usr/bin/python3.12

import argparse

import snapshot
import checkout

# TODO: Snapshot of python packages -> Conclusion: People needs to create a
# venv, Pipfile.lock, etc and version control these files in order to snapshot
# the python packages.

# TODO: Snapshot of javascript packages -> Conclusion: use npm-lock.json

# TODO: Snapshot which spack repos packages are coming from?

# TODO: Improve error handling


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
    # snapshot.snapshot(args.work_dir, verbose=True)
    checkout.checkout(args.work_dir, verbose=True)
    # args.func(args)


if __name__ == "__main__":
    main()
