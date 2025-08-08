import os
import subprocess
from pathlib import Path
from graphlib import TopologicalSorter


def construct_hash_table() -> dict[str, set[str]]:
    work_dir = Path(__file__).expanduser().resolve()
    print(work_dir)


construct_hash_table()
