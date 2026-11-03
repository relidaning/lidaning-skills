"""Link a complete skill; migrate the installer's old Markdown-only layout."""
import sys
from pathlib import Path

source, target = (Path(p).absolute() for p in sys.argv[1:])
source = source.resolve()
if target.is_symlink():
    target.unlink()
elif target.exists():
    if not target.is_dir():
        raise SystemExit(f"Refusing to replace existing file: {target}")
    entries = list(target.iterdir())
    # Only migrate links created by the former installer, including stale ones.
    if any(not p.is_symlink() or p.readlink().parent != source for p in entries):
        raise SystemExit(f"Refusing to replace non-installer files in {target}")
    for entry in entries:
        entry.unlink()
    target.rmdir()
target.symlink_to(source, target_is_directory=True)
