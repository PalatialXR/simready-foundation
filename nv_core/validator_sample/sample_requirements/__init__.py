# Auto-imports all rule modules from this folder so their @register_rule decorators execute.

from importlib import import_module
from pathlib import Path

for _f in Path(__file__).parent.glob("*.py"):
    if _f.name.startswith("_"):
        continue
    import_module(f".{_f.stem}", __package__)
