# Third-party notices

The lightweight conversation annotation UI in web/src/Annotations.tsx,
web/src/annotation-ranges.ts and web/src/conversation-tools.css adapts interaction,
positioning, range lookup and styling patterns from dsh-annotation-core
(local reference version 0.3.12-dsh02.2).

Upstream: https://github.com/linmu115/dsh-annotation-core

MIT License

Copyright (c) 2026 gyixuan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Bundled Windows runtime

The portable v0.1 distribution includes unmodified Node.js 24.7.0 and CPython
3.12.11 executables. Their license notices are included in
`licenses/Node.js-24.7.0-LICENSE.txt` and
`licenses/Python-3.12.11-LICENSE.txt`, as well as their runtime folders.
The CPython Windows build comes from the locally installed uv-managed
python-build-standalone distribution; its additional runtime license files
are retained in `runtime/python`.

JavaScript packages retain their own LICENSE/NOTICE files under `node_modules`.
Python packages retain their license metadata under `runtime/python/Lib/site-packages`.
Exact dependency versions are recorded in `package-lock.json` and
`requirements.lock.txt`. The narrow brace-expansion repair uses the verified
upstream package stored under `vendor/`; see `scripts/fix_dependency.mjs`.

Financial report samples retain their original publishers' copyright and
disclosure sources. Sample source URLs and hashes are recorded in their
manifests. The private distribution does not relicense these reports.
