# Security Policy

## Supported Versions

| Version | Security fixes |
|---|---|
| 1.x | Yes |
| 0.x | No |

## Reporting

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting for
`https://github.com/li-neo/one-skills`, and include:

- affected version and commit;
- reproduction steps or a minimal Pack;
- expected impact;
- whether credentials, private sources, or destructive actions are involved.

Do not include live credentials or private source content. Replace them with
minimal synthetic fixtures.

## Response Targets

- acknowledgement: within 3 business days;
- initial severity assessment: within 7 business days;
- remediation timeline: based on severity and exploitability.

## Security Boundaries

Stable Core 1.0 covers local CLI, Pack files, SQLite workspace, validation,
evaluation gates, install, and export. HTTP API, Worker, PostgreSQL, S3,
plugins, and automatic evolution remain experimental and require an
independent deployment security review.
