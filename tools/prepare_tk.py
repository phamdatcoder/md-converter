"""Stage the installed Tcl/Tk resources for source runs and Windows builds."""

import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = Path(sys.base_prefix) / "tcl"
if source.is_dir():
    shutil.copytree(source, root / ".build-tools/tcl", dirs_exist_ok=True)
