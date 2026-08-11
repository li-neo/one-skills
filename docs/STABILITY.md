# Stability and Compatibility

## Stable Core 1.0

The following contracts follow Semantic Versioning throughout 1.x:

- local CLI: `init`, `distill`, `inspect`, `update`, `semantic`, `compile`,
  `evaluate`, `compare`, `validate`, `release`, `install`, `export`, and
  `migrate`;
- Pack Schema 1.0 and authoritative Pack assets;
- SQLite workspace and local retrieval;
- source, evidence, Overview, Portfolio, Compiler, evaluation, install, and
  export behavior;
- migration from Pack 0.2, 0.3, and 0.4.

Stable fields and commands are not removed in 1.x. A deprecation remains
available for at least one minor release before removal in a future major
version.

## Experimental

The following modules ship for engineering evaluation but are not covered by
the 1.x compatibility promise:

- HTTP API and remote Worker deployment;
- PostgreSQL and S3 adapters;
- plugin trust and third-party Profile loading;
- automatic evolution;
- generalized quality claims across all seven Profiles.

Experimental does not mean exempt from security checks. It means the contract,
operational recovery evidence, and compatibility surface may still change.

## Quality Claim

Version 1.0 claims engineering stability for Stable Core. It does not claim
that all seven distillation Profiles have proven stable task effectiveness.

The Mao case retains a frozen 60-case development comparison. Its historical
Answer and Judge used shared-model, session-separated execution, so Stable
delivery correctly refuses to treat it as independent release evidence until
it is rerun with provider-separated or model-separated roles.
