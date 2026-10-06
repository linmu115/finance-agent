"""Large run inputs stored once per distinct content.

Each analysis or cleaning run used to write its own full copy of the project's
pages, tables, facts and research records, and the sandbox then copied them a
second time. Identical bytes are now kept once under
``exports/<project>/.snapshots/<sha256>`` and appear in every run folder as a
hard link: the run folders look exactly as before and cost no extra disk.

On a volume without hard links (or at the per-file link limit) a run gets its
own ordinary copy, which is the previous layout.
"""
from __future__ import annotations
import hashlib
import os
import threading
import uuid
from pathlib import Path

# The sandbox launcher links, rather than copies, inputs found in a folder of
# this name (sandbox.launcher.SHARED_FOLDER).
SHARED_FOLDER = '.snapshots'

# One service process owns the data directory; this only orders its own threads.
_lock = threading.Lock()


def write_input(exports: Path, project_id: str, destination: Path, data: bytes) -> Path:
    """Write ``data`` as ``destination`` and return the file to hand to the sandbox.

    The returned path is the shared snapshot when the run folder could link to
    it, so the sandbox can link as well; otherwise it is ``destination`` itself.
    """
    folder = exports / project_id / SHARED_FOLDER
    shared = folder / (hashlib.sha256(data).hexdigest() + destination.suffix)
    with _lock:
        created = not shared.is_file()
        if created:
            folder.mkdir(parents=True, exist_ok=True)
            temporary = folder / (uuid.uuid4().hex + '.tmp')
            with open(temporary, 'wb') as file:
                file.write(data)
                # On disk before the content name exists: a file cut short by a power failure
                # would otherwise be reused by every later run with the same data.
                file.flush()
                os.fsync(file.fileno())
            if os.name != 'nt':
                # Readable by the sandbox user, writable by nobody.
                temporary.chmod(0o444)
            os.replace(temporary, shared)
        try:
            os.link(shared, destination)
            return shared
        except OSError:
            if created:
                # Nothing links here: keep one copy, inside the run folder.
                os.replace(shared, destination)
            else:
                destination.write_bytes(data)
            return destination


def remove_unreferenced(exports: Path, project_id: str) -> list[str]:
    """Delete snapshots that no run folder links to any more."""
    folder = exports / project_id / SHARED_FOLDER
    removed = []
    with _lock:
        if not folder.is_dir():
            return removed
        for entry in folder.iterdir():
            if entry.is_file() and entry.stat().st_nlink == 1:
                entry.unlink()
                removed.append(entry.name)
    return sorted(removed)
