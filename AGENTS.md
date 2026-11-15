# IDML renderer — instructions for agents

This repository is a Rust headless IDML-to-PNG/PDF renderer derived from DesignCraft. Read
[ROADMAP.md](ROADMAP.md) and [docs/gaps.md](docs/gaps.md) at the start of each session.

- Preserve no-panic and clean-room behavior and respect asset attribution and licences. Input is hostile:
  bound allocations and recursion, use checked arithmetic, and report failures.
- Keep the native renderer headless and preserve WASM compatibility of the retained libraries.
- Fonts are optional external build inputs from `storytold/craft-fonts`; do not add font files to
  this repository. Existing bundled Latin fonts are retained and attributed in ASSETS.md.
- Run `cargo xtask ci` before committing. This checks formatting, PDF dependencies, clippy, tests,
  asset attribution, dependency layers and the retained WASM-safe libraries.
- For rendering changes, test the affected behavior and compare representative output. Real
  proprietary documents and their images stay outside the repository.
- Update ROADMAP.md and docs/gaps.md when renderer behavior or its known limits change.
