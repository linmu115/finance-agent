Finance Agent 0.3.0 - Windows x64

1. Extract the whole ZIP into a writable folder.
2. Double-click install.cmd. Node.js, Python and dependencies are included.
3. Save your own model/search API settings in the application.

Start: start-finance.cmd
Stop: stop-finance.cmd
Check: check-install.cmd
Default page: http://127.0.0.1:3001/

Chinese deployment and usage guide: docs/START_AND_USE.md
Release notes and verification: docs/RELEASE-0.3.0.md
Technical paper: paper/v0.3.0/finance-agent-technical-paper.pdf
Default data: data/active/ (version 0.1 used data/; see the upgrade guide).
Use one service on port 3001. Stop the verified previous instance before upgrading.
Samples and analysis questions: samples/native-pdf/

The package contains no API keys or user data.
Docker is required for the default script-based financial ingestion and arbitrary Python analysis. It is not started automatically. Existing-data queries and built-in financial models can run without Docker. See README.md for the image setup.
