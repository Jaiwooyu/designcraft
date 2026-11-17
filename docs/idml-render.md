# Headless IDML renderer

`idml-render` is the default Cargo target. It loads an IDML package and writes PNG pages, a PDF,
 or both without starting the desktop application or the editing engine. `--analysis FILE.json`
additionally writes [source-format observations](editorial-analysis.md), and can be used on its own.

```sh
cargo build --release
./target/release/idml-render --in input.idml --png-dir rendered --pdf rendered/output.pdf \
  --fallback-font 'Noto Sans CJK KR'
```

Install a Korean sans font on the server first. The renderer selects an installed Apple SD Gothic
Neo, Malgun Gothic, Noto Sans CJK KR, Noto Sans KR, or Source Han Sans K automatically; the option
chooses a specific installed family instead. The renderer substitutes missing families in memory;
it does not rewrite the IDML. Font metrics may change line breaks and cause text to overflow.
The option reports substituted fonts; missing linked files and text that does not fit are reported
on stderr. Some
complex parent-page overset and unsupported IDML features may not be reported.

Put linked files beside the IDML or in its `Links` folder. Subfolders inside `Links` are supported.
For safety, links and document fonts are read only within that folder, including after resolving
symbolic links. `Document Fonts` is detected case-insensitively. Each input and linked file is
limited to 256 MiB. PNG output includes document bleed; `--scale 2` renders two pixels per point.
PDF output uses the default print export options, with no bleed or marks.

The renderer currently makes one process per invocation. It has not been benchmarked on the target
server, and direct IDML editing and an agent feedback loop are not implemented. For placed PDFs,
some non-default crop-box handling remains in the desktop engine and has not yet been carried
across. Check important layouts against a reference before depending on this renderer.
