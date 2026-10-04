"""Stdio child ownership and shutdown. No Store is opened by this module.

The service owns a kernel file lock until its actual writers have stopped. A
dead Node parent releasing its own guard therefore cannot permit a second
Python service to run recovery while the old child is still draining work.
"""
from __future__ import annotations
import os
import sys
import threading
from pathlib import Path


class ServiceOwnership:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._file = open(self.root / '.finance-service.lock', 'a+b', buffering=0)
        self._locked = False
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(self._file.fileno()).st_size == 0:
                    self._file.write(b'\0')
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
        except OSError as exc:
            self._file.close()
            raise RuntimeError('service_data_directory_in_use') from exc

    def close(self):
        if self._file.closed:
            return
        try:
            if self._locked:
                if os.name == 'nt':
                    import msvcrt
                    self._file.seek(0)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                self._locked = False
        finally:
            self._file.close()
        # Keep the inode: unlinking it permits another process to lock a new
        # file while a previous waiter still refers to the old inode.

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


POOL_NAMES = ('processing_pool', 'pool', 'analysis_pool', 'embedding_pool')
FLAG_NAMES = ('processing_flags', 'cancel_flags', 'analysis_flags')


def request_service_shutdown(service):
    """Stop accepting work and signal all owned jobs as soon as stdin hits EOF."""
    event = getattr(service, '_service_shutdown', None)
    if event is None:
        event = service._service_shutdown = threading.Event()
    event.set()
    # Disable future submissions before taking a snapshot of active flags.
    for name in POOL_NAMES:
        pool = getattr(service, name, None)
        if pool:
            pool.shutdown(wait=False, cancel_futures=True)
    for name in FLAG_NAMES:
        for flag in list(getattr(service, name, {}).values()):
            flag.set()
    # A running sandbox is not cancelled merely by setting its pre-start flag.
    # Use the normal project-bound cancellation path to stop its container.
    for run_id in list(getattr(service, 'analysis_flags', {})):
        try:
            with service.store.connect() as db:
                row = db.execute('SELECT project_id FROM analysis_jobs WHERE run_id=?', (run_id,)).fetchone()
            if row:
                service.cancel_analysis(row[0], run_id)
        except Exception as exc:
            # Ownership remains held, and the executor wait below still prevents
            # a replacement service until this task really finishes.
            print('Service shutdown: analysis cancellation pending (' + type(exc).__name__ + ')', file=sys.stderr)


def shutdown_service(service):
    request_service_shutdown(service)
    for name in POOL_NAMES:
        pool = getattr(service, name, None)
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)


class _EofStdin:
    def __init__(self, stream, service):
        self.stream = stream
        self.service = service

    def __aiter__(self):
        return self

    async def __anext__(self):
        line = await self.stream.readline()
        if line:
            return line
        import anyio
        await anyio.to_thread.run_sync(request_service_shutdown, self.service)
        raise StopAsyncIteration


def run_service_stdio(mcp, service, ownership):
    import anyio
    from io import TextIOWrapper
    from mcp.server.stdio import stdio_server

    async def serve():
        stream = _EofStdin(anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding='utf-8')), service)
        # Equivalent to FastMCP.run_stdio_async with an EOF-aware input adapter.
        async with stdio_server(stdin=stream) as (read_stream, write_stream):
            await mcp._mcp_server.run(read_stream, write_stream, mcp._mcp_server.create_initialization_options())

    try:
        anyio.run(serve)
    finally:
        # Never unlock on a timeout while a worker may still write. A slow task
        # leaves a visible unavailable workspace, not two competing services.
        shutdown_service(service)
        ownership.close()
