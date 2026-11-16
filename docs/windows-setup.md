# Windows setup

Install Git and Visual Studio's **Desktop development with C++** workload, including the MSVC
x64/x86 tools and a Windows SDK. Install Rust 1.95 or newer using the official
[64-bit rustup installer](https://rust-lang.org/tools/install/), then open a new PowerShell window
so its PATH includes `%USERPROFILE%\.cargo\bin`.

Install the development tools and the target used by the repository's WASM checks:

```powershell
rustup component add rustfmt clippy rust-analyzer
rustup target add wasm32-unknown-unknown
rustc --version
cargo --version
```

From the repository directory, build and run:

```powershell
Set-Location D:\project\designcraft
cargo build --release --locked
.\target\release\idml-render.exe --in 'C:\path\input.idml' --png-dir '.\outputs\pages' --pdf '.\outputs\layout.pdf' --fallback-font 'Malgun Gothic'
```

Replace the input path with your IDML file. Keep its linked images beside it or in its `Links`
folder. Malgun Gothic (맑은 고딕) is supplied with Korean Windows installations; use another
installed Korean font family if needed. Optional `craft-fonts` inputs are not required to run
the renderer, and font files must stay outside this repository.

Run the full repository checks with:

```powershell
cargo xtask ci
```

If `cargo` is unavailable in a terminal opened before installation, either restart that terminal
or refresh its current PATH for this session:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
```

The first build downloads the locked dependencies from crates.io and GitHub and can take several
minutes. Later builds reuse the Cargo cache and `target` directory.
