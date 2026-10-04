"""A real MCP/Store child with a deliberately slow cancellable writer; temp only."""
import json
import os
import tempfile
import threading
import time
import sys
import faulthandler
import asyncio
from pathlib import Path

data = Path(os.environ['FINANCE_DATA_DIR']).resolve()
assert data.parent.name.startswith('finance-service-lifecycle-')
assert data.parent.parent == Path(tempfile.gettempdir()).resolve()
folder = data.parent
debug_file = open(folder/'child-stderr.log', 'a', encoding='utf-8')
faulthandler.enable(file=debug_file)
faulthandler.dump_traceback_later(9, file=debug_file)
from service.server import service, mcp, ownership
from service.lifecycle import run_service_stdio
from service.store import dumps, utcnow


@mcp.tool()
async def fixture_slow_writer(default_executor: bool = False) -> dict:
    service.create_project('fixture', 'Private lifecycle test')
    flag = threading.Event()
    if not default_executor:
        service.processing_flags['fixture_processing'] = flag
    state = {'processing_id':'fixture_processing','owner_run_id':'fixture_owner','project_id':'fixture','state':'normalizing'}
    with service.store.connect(write=True) as db:
        db.execute('INSERT INTO processing_runs VALUES(?,?,?,?,?,?)', ('fixture_processing','fixture','fixture_owner',dumps(state),utcnow(),utcnow()))
    def worker():
        (folder/'worker-log').write_text('started '+str(time.time())+'\n',encoding='utf-8')
        (folder/'worker-started').write_text(str(os.getpid()), encoding='utf-8')
        if default_executor:
            deadline = time.monotonic()+40
            while not (getattr(service,'_service_shutdown',None) and service._service_shutdown.is_set()) and time.monotonic()<deadline:
                time.sleep(.03)
            shutdown_seen = bool(getattr(service,'_service_shutdown',None) and service._service_shutdown.is_set())
            cancelled = False  # An ordinary to_thread write has no job cancellation flag.
        else:
            cancelled = shutdown_seen = flag.wait(40)
        with open(folder/'worker-log','a',encoding='utf-8') as out: out.write('cancel '+str(time.time())+'\n')
        (folder/'cancel-observed').write_text(str(shutdown_seen), encoding='utf-8')
        deadline = time.monotonic()+40
        while not (folder/'release-worker').exists() and time.monotonic()<deadline:
            time.sleep(.03)
        state['state'] = 'cancelled' if cancelled else 'completed'
        with open(folder/'worker-log','a',encoding='utf-8') as out: out.write('writing '+str(time.time())+'\n')
        with service.store.connect(write=True) as db:
            db.execute('UPDATE processing_runs SET state_json=?,updated_at=? WHERE processing_id=?', (dumps(state),utcnow(),'fixture_processing'))
        (folder/'worker-finished').write_text(json.dumps(state),encoding='utf-8')
    if default_executor:
        await asyncio.to_thread(worker)
    else:
        service.processing_pool.submit(worker)
    return {'started':True}


try:
    run_service_stdio(mcp, service, ownership)
finally:
    with open(folder/'worker-log','a',encoding='utf-8') as out: out.write('exited '+str(time.time())+'\n')
    faulthandler.cancel_dump_traceback_later()
    (folder/'service-exited').write_text('closed', encoding='utf-8')
