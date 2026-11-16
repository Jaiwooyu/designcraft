# Known gaps

- The FastAPI wrapper is an initial single-instance service with a shared optional bearer token;
  user accounts, tenant isolation, distributed workers and automatic result expiry are not implemented.
  Output quotas are monitored rather than hard OS resource limits. Its Linux container and deployment
  fidelity still require validation; see [the API guide](render-api.md).

- Korean substitute fonts do not have the original fonts' metrics. The supplied newspaper example
  still reports 25 characters of overset text with Apple SD Gothic Neo; other substitutes can
  produce different line breaks and more overset.
- Missing linked files are warned about, not recovered. Package them beside the IDML or in `Links`.
- Import and output are not guaranteed to reproduce every IDML feature. Placed PDFs with non-default
  crop boxes and some parent-page overset cases need additional work and regression tests.
- Linux deployment, performance and real-document fidelity have not been measured yet.
- The retained shared CI workflow has not yet been verified on the new fork. Local checks run
  with `cargo xtask ci`.
- Direct IDML article editing and a render–review–edit loop are not implemented.
