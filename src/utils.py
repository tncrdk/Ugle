from pathlib import Path


# ====================================================================================
# Utils
# ====================================================================================


def check_if_file_exists(filename: Path) -> tuple[bool, str]:
    """Check if file exists (as a file)

    ---
    Args:
        filename : `Path`
            The filename to check the existence of

    ---
    Returns:
        `tuple[bool, str]`
            If the file exists, it will return [True, ""]. Otherwise [False, <err_msg>]
    """
    if not filename.exists():
        return (False, f"{filename.resolve()} does not exist.")
    if not filename.is_file():
        return (False, f"{filename.resolve()} is not a file.")
    return (True, "")


def create_absolute_path(path: Path, work_dir: Path) -> Path:
    """Create an absolute path from `path` rooted in `work_dir`

    ---
    Args:
        path : `Path`
            The directory where the snapshot will be recreated at.

        work_dir: `Path`
            The parent directory of the TOML-file the current snapshot is based on

    ---
    Returns:
        `Path`
            The created absolute path
    """
    path = path.expanduser()
    if not path.is_absolute():
        return (work_dir / path).resolve()
    return path


def verbose_print(verbose: bool, msg: str) -> None:
    """Print `msg` if `verbose` is True

    ---
    Args:
        verbose : `bool`, default 'False'
            Verbose printing

        msg : `str`
            Message to print if verbose is True
    ---
    Returns:
        None
    """
    if verbose:
        print(msg)
