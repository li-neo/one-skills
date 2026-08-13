# one-skills 1.0.0

First Stable Core release of the evidence-first capability distillation
platform.

## Stable

- local CLI and Pack 1.0 protocol;
- SQLite workspace, source/version/evidence lifecycle;
- Overview, Portfolio, Compiler, validation, evaluation gates;
- Pack 0.2/0.3/0.4 migration;
- install and runtime export.

## Experimental

- HTTP API and remote Worker deployment;
- PostgreSQL, S3, and plugin trust;
- automatic evolution;
- generalized effectiveness claims for all seven Profiles.

## Engineering Evidence

- 62 unit and integration tests;
- 87.73% Stable Core aggregate line coverage (85% release gate);
- Pack migration interruption, rollback, lock, revision, and revocation
  fault-injection coverage;
- Python 3.10/3.11/3.12 plus macOS and Windows CI;
- wheel/sdist metadata, resource manifest, and isolated install smoke;
- Mao Pack: 0 validation errors, 0 warnings, and frozen 60-case development
  comparison.

The Mao comparison used shared-model, session-separated Answer/Judge runs. It
is retained as development evidence, not independent Stable Pack proof.
Stable delivery requires provider-separated or model-separated evaluation.

## Artifacts

The GitHub Release contains:

- `one_skills-1.0.0-py3-none-any.whl`;
- `one_skills-1.0.0.tar.gz`;
- `SHA256SUMS`.

No PyPI package or Docker image is published for 1.0.0.
