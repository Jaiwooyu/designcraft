//! Bounded, non-recursive folder analysis, with a fresh process for each document.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::Command;

const MAX_DOCUMENTS: usize = 1_000;
const MAX_ENTRIES: usize = 100_000;

pub(super) struct Options {
    pub input_dir: PathBuf,
    pub analysis_dir: PathBuf,
    pub fallback: Option<String>,
}

fn inputs(root: &Path) -> Result<Vec<PathBuf>, String> {
    let entries = std::fs::read_dir(root).map_err(|e| format!("{}: {e}", root.display()))?;
    let mut paths = Vec::new();
    for (index, entry) in entries.enumerate() {
        if index >= MAX_ENTRIES {
            return Err(format!("batch: directory exceeds {MAX_ENTRIES} entries"));
        }
        let entry = entry.map_err(|e| format!("{}: {e}", root.display()))?;
        let kind = entry.file_type().map_err(|e| format!("{}: {e}", entry.path().display()))?;
        // Do not traverse subdirectories or follow file symlinks out of the selected folder.
        if !kind.is_file() || !entry.path().extension().is_some_and(|ext| ext.eq_ignore_ascii_case("idml")) {
            continue;
        }
        if paths.len() >= MAX_DOCUMENTS {
            return Err(format!("batch: directory exceeds {MAX_DOCUMENTS} IDML files"));
        }
        paths.push(entry.path());
    }
    paths.sort();
    if paths.is_empty() {
        return Err(format!("{}: no IDML files found (subdirectories are not scanned)", root.display()));
    }
    Ok(paths)
}

fn outputs(paths: &[PathBuf], dir: &Path) -> Result<Vec<PathBuf>, String> {
    let sources: BTreeSet<_> = paths.iter().map(|p| p.canonicalize().map_err(|e| format!("{}: {e}", p.display()))).collect::<Result<_, _>>()?;
    let mut names = BTreeSet::new();
    let mut destinations = BTreeSet::new();
    let mut outputs = Vec::new();
    for path in paths {
        let mut name = path.file_stem().ok_or("batch: input has no file stem")?.to_os_string();
        name.push(".json");
        // Refuse colliding stems (including case-only differences) before writing any reports.
        if !names.insert(name.to_string_lossy().to_lowercase()) {
            return Err(format!("batch: duplicate output name: {}", name.to_string_lossy()));
        }
        let output = dir.join(name);
        let resolved = super::output_path(&output)?;
        if sources.contains(&resolved) || !destinations.insert(resolved) {
            return Err(format!("batch: output aliases an input or another output: {}", output.display()));
        }
        outputs.push(output);
    }
    Ok(outputs)
}

pub(super) fn run(opts: Options) -> Result<(), String> {
    let root = opts.input_dir.canonicalize().map_err(|e| format!("{}: {e}", opts.input_dir.display()))?;
    let paths = inputs(&root)?;
    std::fs::create_dir_all(&opts.analysis_dir).map_err(|e| format!("{}: {e}", opts.analysis_dir.display()))?;
    let dir = opts.analysis_dir.canonicalize().map_err(|e| format!("{}: {e}", opts.analysis_dir.display()))?;
    let outputs = outputs(&paths, &dir)?;
    let executable = std::env::current_exe().map_err(|e| format!("batch: cannot locate renderer: {e}"))?;
    let total = paths.len();
    let mut failed = 0;
    for (index, (input, output)) in paths.iter().zip(&outputs).enumerate() {
        eprintln!("[{}/{total}] analyzing {}", index + 1, input.display());
        // Fonts and renderer caches are process-local: memory is released after each file.
        let mut command = Command::new(&executable);
        command.arg("--in").arg(input).arg("--analysis").arg(output);
        if let Some(family) = &opts.fallback {
            command.arg("--fallback-font").arg(family);
        }
        match command.status() {
            Ok(status) if status.success() => {}
            result => {
                failed += 1;
                let reason = match result {
                    Ok(status) => status.to_string(),
                    Err(error) => error.to_string(),
                };
                eprintln!("batch: failed {}: {reason}", input.display());
            }
        }
    }
    eprintln!("batch: {} succeeded, {failed} failed, {total} total", total - failed);
    if failed == 0 { Ok(()) } else { Err("batch: some files failed; see errors above".into()) }
}
