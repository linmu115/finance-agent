"""Native PDF parsing in its own process; Pi remains the job owner.

PyMuPDF's table finder has process-global CHARS/EDGES buffers. Concurrent
documents therefore use separate processes, while progress is streamed back.
"""
from __future__ import annotations
import json
import os
import sys
import uuid
from pathlib import Path
from .parser import parse_document


def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)


def main():
    config=json.loads(sys.stdin.readline())
    try:
        if config.get("operation")=="render_page":
            import fitz
            target=Path(config["target"])
            temporary=target.with_name(target.stem+"."+uuid.uuid4().hex+".png")
            try:
                with fitz.open(config["path"]) as document:
                    page=document[int(config["page"])-1]
                    page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(temporary)
                # Publish only a complete PNG; simultaneous requests for the
                # same page may share the first completed immutable result.
                try:os.link(temporary,target)
                except FileExistsError:pass
            finally:temporary.unlink(missing_ok=True)
            emit({"type":"result","rendered":True})
            return 0
        parsed=parse_document(Path(config["path"]),config["name"],
                              lambda p,m:emit({"type":"progress","progress":p,"message":m}),
                              lambda:False,config.get("options",{}))
        emit({"type":"result","parsed":parsed})
    except Exception as exc:
        # Do not serialize request configuration, URLs, or exception frame locals.
        emit({"type":"error","code":type(exc).__name__})
        return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
