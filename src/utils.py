from pathlib import Path


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


def verbose_print(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg)
