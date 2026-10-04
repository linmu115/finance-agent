"""Image entrypoint; kernel/container restrictions are the security boundary."""
import os
import resource
import runpy

# Limits supplement host monitoring; this is not a replacement for Docker isolation.
resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
os.umask(0o077)
runpy.run_path('/input/__analysis__.py', run_name='__main__')
