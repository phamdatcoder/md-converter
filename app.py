"""Entry point used both from source and by the one-file Windows build."""

from __future__ import annotations

import sys
import os
from pathlib import Path


def main() -> int:
    if not getattr(sys, "frozen", False):
        local_package = Path(__file__).resolve().parent / "markitdown-main" / "packages" / "markitdown" / "src"
        sys.path.insert(0, str(local_package))
        staged_tcl = Path(__file__).resolve().parent / ".build-tools/tcl"
        for variable, name in [("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")]:
            if (staged_tcl / name).is_dir():
                os.environ[variable] = str(staged_tcl / name)
    try:
        from desktop.windows_runtime import preload_cpp_runtime

        preload_cpp_runtime()
        if "--self-test" in sys.argv:
            from desktop.smoke import main as smoke_main

            return smoke_main(sys.argv[sys.argv.index("--self-test") + 1:])
        if "--gui-self-test" in sys.argv:
            from desktop.gui_smoke import main as gui_smoke_main

            return gui_smoke_main(sys.argv[sys.argv.index("--gui-self-test") + 1:])
        from desktop.gui import ConverterApp

        ConverterApp().mainloop()
        return 0
    except Exception as error:
        message = f"Không khởi động được MD Converter:\n\n{error}"
        if "--self-test" in sys.argv or "--gui-self-test" in sys.argv:
            if "--report" in sys.argv:
                import json

                report_path = Path(sys.argv[sys.argv.index("--report") + 1])
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps({"passed": False, "errors": [message]}), encoding="utf-8")
            return 1
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "MD Converter", 0x10)
        else:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
