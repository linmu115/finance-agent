"""Host-owned scientific analysis runner. Never executes analysis on the host."""

from .launcher import SandboxRunner, RunnerError

def create_runner(state_root):
    """Select a local Docker engine or the explicitly bootstrapped local Linux VM."""
    import os
    from pathlib import Path
    config = Path(os.environ.get("FINANCE_SANDBOX_REMOTE_CONFIG", str(Path(__file__).parent / "runtime" / "remote.json")))
    if config.is_file():
        from .remote import RemoteSandboxRunner
        return RemoteSandboxRunner(state_root, config)
    return SandboxRunner(state_root)


__all__ = ["SandboxRunner", "RunnerError", "create_runner"]
