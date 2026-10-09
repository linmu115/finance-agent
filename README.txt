Finance Agent 0.4.0 - Windows x64

1. Extract the whole ZIP into a writable folder.
2. Double-click install.cmd. Node.js, Python and dependencies are included.
3. Save your own model/search API settings in the application.

Start: start-finance.cmd
Stop: stop-finance.cmd
Check: check-install.cmd
Default page: http://127.0.0.1:3001/

Chinese deployment and usage guide: docs/START_AND_USE.md
Release notes and verification: docs/RELEASE-0.4.0.md
Evaluation and known limitations: docs/RELEASE-0.4.0.md
Default data: data/active/ (version 0.1 used data/; see the upgrade guide).
Use one service on port 3001. Stop the verified previous instance before upgrading.
Upload your own reports; the package contains only a small public PDF parsing fixture.

The package contains no API keys or user data.
Docker is required for the default script-based financial ingestion and arbitrary Python analysis. It is not started automatically. Existing-data queries and built-in financial models can run without Docker. See README.md for the image setup.
