#!/usr/bin/python3.12

import argparse

import snapshot
import checkout

# TODO: Snapshot which spack repos packages are coming from?

# TODO: Improve error handling


# ====================================================================================
# Program
# ====================================================================================


def checkout_handler(args) -> None:
    checkout.checkout(args.work_dir, args.verbose)


def snapshot_handler(args) -> None:
    snapshot.snapshot(args.work_dir, args.verbose)


def main():
    parser = argparse.ArgumentParser("Ugle", description="Create and retrieve snapshot")
    # work_dir is the "root" of the snapshot.
    # parser.add_argument("work_dir", help="The directory where the ugle.toml file is located.")
    subparsers = parser.add_subparsers()
    checkout_parser = subparsers.add_parser("checkout")
    snapshot_parser = subparsers.add_parser("snapshot")
    #
    checkout_parser.add_argument(
        "work_dir", help="The directory where the ugle.toml file is located."
    )
    checkout_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose printing"
    )
    checkout_parser.set_defaults(func=checkout_handler)

    snapshot_parser.add_argument(
        "work_dir", help="The directory where the ugle.toml file is located."
    )
    snapshot_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose printing"
    )
    snapshot_parser.set_defaults(func=snapshot_handler)

    args = parser.parse_args()
    # print(args.work_dir)
    # snapshot.snapshot(args.work_dir, verbose=True)
    # checkout.checkout(args.work_dir, verbose=True)
    args.func(args)


if __name__ == "__main__":
    main()
