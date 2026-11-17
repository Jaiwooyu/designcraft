# IDML headless renderer

A Rust command-line renderer built from DesignCraft's IDML importer, composition engine and
PNG/PDF renderers. It runs without InDesign, a windowing system or a GPU.

```sh
cargo build --release
./target/release/idml-render --in input.idml --png-dir output --pdf output/layout.pdf
```

Install an available Korean sans font on the server, for example Noto Sans CJK KR, to substitute
missing fonts. Specify `--fallback-font 'Noto Sans CJK KR'` to select a family explicitly.
Linked images should be beside the IDML or in its `Links` folder. The renderer warns about
missing links and overset text. Font substitution can change layout.

Extract source-format observations and evidence as JSON, with optional rendered pages:

```sh
cargo run -p idml-render -- --in input.idml --analysis analysis.json --png-dir pages
```

The report keeps original formats separate from rendered measurements and marks format candidates
as needing review. It does not call an AI service or infer editorial policies.
See [editorial analysis](docs/editorial-analysis.md) for the schema, bounds and limitations.

The renderer has been checked with one real newspaper IDML on macOS. An image missing from that
package and 25 overset characters remain in that example. Linux server performance and fidelity
have not yet been measured. For options and limitations see [the renderer guide](docs/idml-render.md)
and [known gaps](docs/gaps.md).

Run `cargo xtask ci` before committing. The project uses Rust 1.95 or newer and is licensed under
MIT or Apache-2.0; see [ASSETS.md](ASSETS.md) and [NOTICE](NOTICE) for asset and dependency credits.
