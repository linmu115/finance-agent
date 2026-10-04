Dependency integrity repair
===========================

Pi 1.0.0 publishes npm-shrinkwrap.json that pins its nested brace-expansion to
5.0.9. npm 11.19.0 ignored both a root global override and a package-scoped
override for that pin. This was reproduced with package-lock-only install in an
isolated project copy. npm documentation permits published shrinkwraps to dictate
dependency resolution; therefore an override declaration alone was not treated
as proof of remediation.

The narrow postinstall repair uses the official brace-expansion 5.0.12 tarball in
vendor/. Its SHA-512 matches the npm registry dist.integrity saved in
registry-dist.json. The script verifies integrity before extracting exactly 13
ordinary files and updates only the matching entries in the project lock, npm's
hidden installed lock, and Pi's installed shrinkwrap. It never downloads or runs
package scripts. Unrecognized Pi/dependency versions and symlink paths fail
closed instead of broadening the patch or silently downgrading another version.

Commands
  npm run deps:repair
  npm run deps:check

Normal npm install / npm ci invokes postinstall automatically. If --ignore-scripts
is deliberately used, run deps:repair afterwards. prestart and predev check the
installed package against every verified official file and refuse to run with the
vulnerable or modified package. The same check is included in build/typecheck.

npm ci may print one high advisory in its own summary because npm computes that
summary before root postinstall runs. The repair then fixes the installed package.
Run npm audit after installation to audit the final repaired tree; the clean-CI
explicit audit in the evidence directory reports zero vulnerabilities.

When Pi's upstream shrinkwrap is updated, remove this workaround and verify a
clean install, package tree and audit before deleting the vendored archive.

Evidence
- registry-dist.json: official registry integrity and package metadata.
- audit-before.json: one high severity brace-expansion advisory entry.
- repair-latest.json: verified package, modified file count and lock hashes.
- audit-after.json: post-repair npm audit result.
- reproduction.json: successful normal install, clean CI, repeated install and integrity checks.
- audit-clean-ci.json: explicit audit after the clean-CI postinstall repair (zero vulnerabilities).
- integrity-negative-tests.json: corrupted archive rejected without writes; altered installed file detected and restored.

References
https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#overrides
https://docs.npmjs.com/cli/v11/configuring-npm/npm-shrinkwrap-json/
https://registry.npmjs.org/brace-expansion/5.0.12
https://github.com/advisories/GHSA-q2hr-2g5m-vwhr
https://github.com/advisories/GHSA-qhr7-859c-m2p7
https://github.com/advisories/GHSA-6j4f-fj2g-mc7p
