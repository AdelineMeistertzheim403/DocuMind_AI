# Reviewed build inputs

These public manifests describe inputs qualified on 2026-10-26 for Linux amd64,
CPython 3.13/glibc and PostgreSQL 17/Alpine 3.24. They contain no archives,
credentials, private cache locations or acceptance of residual risks.

- `requirements.runtime.lock`: 44 runtime wheels, exact versions and PyPI SHA-256.
- `requirements.build.lock`: pip/setuptools/wheel/packaging in a dedicated builder.
- `requirements.test.lock`: five Linux test extras, added to the runtime closure.
- `pgvector.json`: exact official commit/source archive and the 19 additional
  compiler APKs required by the pinned PostgreSQL base. Git and its dependencies
  are unnecessary when building the reviewed archive. The base supplies the
  remaining runtime libraries. APK signatures are still required by `apk`.
  `OPTFLAGS=""` uses the upstream portability option instead of compiling for
  the builder's CPU with `-march=native`.

The Python locks are at the repository root. They supplement the existing
cross-platform `requirements.lock`; they do not change application versions.
Tools vendored inside pip/setuptools are covered by their wheel hashes, not by
an independent review of every vendored source. npm continues to use the exact
`frontend/package-lock.json` with `npm ci` and SRI checks; installation scripts
are preserved. Historical signature/provenance decisions remain separate.

Dockerfiles download from public origins available to GitHub runners. No build
depends on `var/`, an existing workstation cache, or a local qualification image.
`tools/fetch_build_materials.py` permits only the reviewed official pgvector and
Alpine paths, rejects redirects, and verifies sizes and hashes. There is no
fallback to a new version, unsigned package or mutable APK index. If an archive
disappears, the build must fail until a newly reviewed manifest is approved.

## Updating safely

Treat the base digests, Python locks, build tools, pgvector source and compiler
packages as a reviewed set. Re-read official release/security information, acquire
new exact archives, verify hashes and available signatures/provenance, and test
the affected builds and security invariants before changing these files. Do not
recompute an expected hash from unreviewed bytes merely to make a build pass.
An update must be visible in a new PR revision and pass the actual CI.

Base pinning removes drift; it does not promise that a pinned release is free of
vulnerabilities or remains suitable indefinitely. Establish an operator-approved
review cadence and support/archive availability policy. No automatic upgrade or
permanent security freeze is introduced here. Native installer keys are inherited
from official base images; independent publisher and builder trust remains a
separate decision. Byte-identical OCI layers are not a release requirement.
