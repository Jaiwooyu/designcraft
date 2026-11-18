//! Workspace checks for the headless IDML renderer.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

mod assets;
mod layers;
mod pdf_deps;

use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).parent().map_or_else(|| PathBuf::from("."), Path::to_path_buf)
}

fn cargo(args: &[&str]) -> Result<(), String> {
    eprintln!("$ cargo {}", args.join(" "));
    let status = Command::new(std::env::var_os("CARGO").unwrap_or_else(|| "cargo".into()))
        .current_dir(root())
        .args(args)
        .status()
        .map_err(|e| e.to_string())?;
    if status.success() { Ok(()) } else { Err(format!("cargo {} failed: {status}", args.join(" "))) }
}

fn metadata() -> Result<serde_json::Value, String> {
    let out = Command::new(std::env::var_os("CARGO").unwrap_or_else(|| "cargo".into()))
        .current_dir(root())
        .args(["metadata", "--format-version", "1", "--no-deps"])
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(format!("cargo metadata: {}", String::from_utf8_lossy(&out.stderr)));
    }
    serde_json::from_slice(&out.stdout).map_err(|e| e.to_string())
}

fn check_layers() -> Result<(), String> {
    let crates = layers::from_metadata(&metadata()?)?;
    let errors = layers::check(&crates);
    if !errors.is_empty() {
        return Err(errors.iter().map(ToString::to_string).collect::<Vec<_>>().join("\n"));
    }
    eprintln!("{} crates: no layering violations", crates.len());
    Ok(())
}

fn wasm() -> Result<(), String> {
    let crates = layers::from_metadata(&metadata()?)?;
    // The command-line host and stdio/TCP MCP server are native entry points. Keep the
    // document, format and editing engine layers (L0–L5) usable from a WASM host.
    let names: Vec<_> =
        crates.iter().filter(|c| matches!(layers::classify(&c.name), Some(layers::Class::Layer(0..=5)))).map(|c| c.name.as_str()).collect();
    let mut args = vec!["check", "--target", "wasm32-unknown-unknown"];
    for name in &names {
        args.extend(["-p", name]);
    }
    cargo(&args)
}

fn ci() -> Result<(), String> {
    cargo(&["fmt", "--all", "--", "--check"])?;
    pdf_deps::run(&root())?;
    cargo(&["clippy", "--workspace", "--all-targets", "--", "-D", "warnings"])?;
    cargo(&["test", "--workspace"])?;
    assets::run(&root())?;
    check_layers()?;
    wasm()
}

fn run() -> Result<(), String> {
    match std::env::args().nth(1).as_deref() {
        Some("ci") => ci(),
        Some("test") => cargo(&["test", "--workspace"]),
        Some("layers") => check_layers(),
        Some("assets") => assets::run(&root()),
        Some("pdf-deps") => pdf_deps::run(&root()),
        Some("wasm") => wasm(),
        None | Some("help" | "--help" | "-h") => {
            eprintln!("usage: cargo xtask <ci|test|layers|assets|pdf-deps|wasm>");
            Ok(())
        }
        Some(other) => Err(format!("unknown command: {other}")),
    }
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}
