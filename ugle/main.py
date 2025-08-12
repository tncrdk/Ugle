#!/usr/bin/python3.12

import argparse

import snapshot
import checkout

# TODO: Snapshot which spack repos packages are coming from?
# TODO: Make the program clean up after itself regardsless of errors thrown


# ====================================================================================
# Program
# ====================================================================================


def checkout_handler(args) -> None:
    """Extract the necessary information to checkout a snapshot

    --
    Args:
        args : Namespace
            The `Namespace` object returned by `parse_args()`

    ---
    Returns:
        None
    """
    args_dict = vars(args)
    checkout.checkout(
        args_dict.get("lock-file"), args_dict.get("destination"), args_dict.get("force"), args.verbose
    )


def snapshot_handler(args) -> None:
    """Extract the necessary information to perform a snapshot

    --
    Args:
        args : Namespace
            The `Namespace` object returned by `parse_args()`

    ---
    Returns:
        None
    """
    snapshot.snapshot(vars(args).get("TOML-file"), args.verbose)


def main():
    """
    Create the cmd-line parser and parse arguments supplied while running this file.
    """
    parser = argparse.ArgumentParser(
        "Ugle", description="Create and retrieve snapshots"
    )
    # work_dir is the "root" of the snapshot.
    subparsers = parser.add_subparsers()
    checkout_parser = subparsers.add_parser("checkout")
    snapshot_parser = subparsers.add_parser("snapshot")

    # Checkout subcommand
    checkout_parser.add_argument(
        "lock-file", help="The lockfile to load the snapshot from"
    )
    checkout_parser.add_argument(
        "-d", "--destination", help="Where to recreate the snapshot", required=False
    )
    checkout_parser.add_argument(
        "-f", "--force", action="store_true", help="If target directories exist, they will be overwritten"
    )
    checkout_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose printing"
    )
    checkout_parser.set_defaults(func=checkout_handler)

    # Snapshot subcommand
    snapshot_parser.add_argument(
        "TOML-file", help="The TOML-file to create the snapshot from"
    )
    snapshot_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose printing"
    )
    snapshot_parser.set_defaults(func=snapshot_handler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
