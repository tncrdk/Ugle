import os
from pathlib import Path


p = Path("~/Code/IFEM/")
p = p.expanduser()
print(p.is_absolute())
print(Path(str(p) + "-habahaba"))
