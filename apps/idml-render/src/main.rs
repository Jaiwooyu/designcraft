//! Headless IDML to PNG and PDF rendering.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]
#![forbid(unsafe_code)]

mod fonts;

use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const MAX_FILE: u64 = 256 * 1024 * 1024;
const USAGE: &str = "usage: idml-render --in FILE.idml [--png-dir DIR] [--pdf FILE.pdf] [--fallback-font FAMILY] [--scale PIXELS_PER_POINT]";

struct Options {
    input: PathBuf,
    png_dir: Option<PathBuf>,
    pdf: Option<PathBuf>,
    fallback: Option<String>,
    scale: f64,
}

fn options(args: impl IntoIterator<Item = String>) -> Result<Options, String> {
    let mut input = None;
    let mut png_dir = None;
    let mut pdf = None;
    let mut fallback = None;
    let mut scale = 1.0;
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if arg == "--help" || arg == "-h" {
            return Err(USAGE.into());
        }
        let value = args.next().filter(|v| !v.starts_with("--")).ok_or_else(|| format!("{arg}: missing value\n{USAGE}"))?;
        match arg.as_str() {
            "--in" => input = Some(PathBuf::from(value)),
            "--png-dir" => png_dir = Some(PathBuf::from(value)),
            "--pdf" => pdf = Some(PathBuf::from(value)),
            "--fallback-font" => fallback = Some(value),
            "--scale" => scale = value.parse::<f64>().ok().filter(|v| v.is_finite() && *v > 0.0).ok_or("--scale must be positive and finite")?,
            _ => return Err(format!("unknown option {arg}\n{USAGE}")),
        }
    }
    let input = input.ok_or_else(|| format!("missing --in\n{USAGE}"))?;
    if png_dir.is_none() && pdf.is_none() {
        return Err(format!("choose --png-dir or --pdf\n{USAGE}"));
    }
    Ok(Options { input, png_dir, pdf, fallback, scale })
}

fn read_capped(path: &Path) -> Result<Vec<u8>, String> {
    let file = std::fs::File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if !file.metadata().map_err(|e| e.to_string())?.is_file() {
        return Err(format!("{}: not a file", path.display()));
    }
    let mut bytes = Vec::new();
    file.take(MAX_FILE + 1).read_to_end(&mut bytes).map_err(|e| format!("{}: {e}", path.display()))?;
    if bytes.len() as u64 > MAX_FILE {
        return Err(format!("{}: file exceeds 256 MiB", path.display()));
    }
    Ok(bytes)
}

/// Packaged links are resolved only beneath the IDML folder, including through symlinks.
fn read_link(root: &Path, link: &str) -> Option<Vec<u8>> {
    if link.len() > 128 * 1024 {
        return None;
    }
    let parts: Vec<_> = link.split(['/', '\\']).filter(|v| !v.is_empty()).collect();
    let valid = |part: &&str| *part != "." && *part != ".." && !part.contains(':');
    let name = parts.last().filter(|part| valid(part))?;
    let mut candidates = vec![root.join("Links").join(name), root.join(name)];
    if let Some(index) = parts.iter().rposition(|part| part.eq_ignore_ascii_case("Links")) {
        let suffix = parts.get(index + 1..)?;
        if !suffix.is_empty() && suffix.iter().all(valid) {
            candidates.insert(0, suffix.iter().fold(root.join("Links"), |path, part| path.join(part)));
        }
    }
    for candidate in candidates {
        let Ok(path) = candidate.canonicalize() else { continue };
        if !path.starts_with(root) {
            continue;
        }
        if let Ok(bytes) = read_capped(&path) {
            return Some(bytes);
        }
    }
    None
}

fn run(opts: Options) -> Result<(), String> {
    let path = opts.input.canonicalize().map_err(|e| format!("{}: {e}", opts.input.display()))?;
    if opts.pdf.as_ref().and_then(|p| p.canonicalize().ok()).is_some_and(|p| p == path) {
        return Err("PDF output must not overwrite the input document".into());
    }
    let root = path.parent().ok_or("input has no parent directory")?;
    let bytes = read_capped(&path)?;
    let missing = std::cell::RefCell::new(std::collections::BTreeSet::new());
    let imported = designcraft_idml::import_idml_report(&bytes, &|link| {
        let data = read_link(root, link);
        if data.is_none() {
            missing.borrow_mut().insert(link.to_string());
        }
        data
    })
    .map_err(|e| e.to_string())?;
    for link in missing.into_inner() {
        eprintln!("warning: linked image not found: {link}");
    }
    for warning in imported.warnings {
        eprintln!("warning: {warning}");
    }
    let mut doc = imported.document;
    let font_folder = std::fs::read_dir(root)
        .ok()
        .into_iter()
        .flatten()
        .flatten()
        .find(|entry| entry.file_name().to_str().is_some_and(|name| name.eq_ignore_ascii_case("Document Fonts")) && entry.path().is_dir())
        .map(|entry| entry.path())
        .unwrap_or_else(|| root.join("Document Fonts"));
    let loaded = designcraft_fonts::FontDb::global().load_document_fonts(&font_folder, &|p| {
        let canonical = p.canonicalize().map_err(|e| e.to_string())?;
        if canonical.starts_with(root) { Ok(()) } else { Err("font path is outside the document folder".into()) }
    });
    doc.font_scope = loaded.scope;
    for warning in loaded.skipped {
        eprintln!("warning: document fonts: {warning}");
    }
    let fallback = opts.fallback.or_else(|| {
        let fonts = designcraft_fonts::FontDb::global().scoped(doc.font_scope);
        ["Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans CJK KR", "Noto Sans KR", "Source Han Sans K"]
            .into_iter()
            .find(|family| fonts.has_family(family))
            .map(str::to_string)
    });
    if let Some(family) = &fallback {
        for original in fonts::replace_missing(&mut doc, family)? {
            eprintln!("warning: replaced missing font {original} with {family}");
        }
    } else {
        eprintln!("warning: no Korean sans fallback is installed; missing fonts may render incorrectly");
    }
    let cache = designcraft_compose::Cache::new();
    for story in doc.stories.values() {
        let Some(frame) = story.frames.last() else { continue };
        if !doc.find(*frame).is_some_and(|location| matches!(location.spread, designcraft_doc::SpreadRef::Doc(_))) {
            continue;
        }
        let composed = cache.get(&doc, story.id, None);
        if let Some(start) = composed.overset_at.filter(|_| composed.is_overset()) {
            let count = story.text.get(start..).map_or(0, |text| text.chars().count());
            if count > 0 {
                eprintln!("warning: {count} character(s) in frame {} do not fit", frame.0);
            }
        }
    }
    if let Some(dir) = opts.png_dir {
        std::fs::create_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
        let mut renderer = designcraft_render::Renderer::new();
        for page in 0..doc.page_count() {
            let image = renderer
                .render_page(&doc, &cache, page, opts.scale, true, &designcraft_render::RenderOptions { printing_only: true, ..Default::default() })
                .ok_or_else(|| format!("page {} cannot be rendered at this scale", page + 1))?;
            let out = dir.join(format!("page-{:03}.png", page + 1));
            craft_atomic::atomic_write(&out, &image.to_png()).map_err(|e| format!("{}: {e}", out.display()))?;
            eprintln!("wrote {} ({}x{})", out.display(), image.width, image.height);
        }
    }
    if let Some(path) = opts.pdf {
        let report = designcraft_pdf::export_pdf_with_report(&doc, &cache, &Default::default()).map_err(|e| e.to_string())?;
        craft_atomic::atomic_write(&path, &report.bytes).map_err(|e| format!("{}: {e}", path.display()))?;
        eprintln!("wrote {} ({} pages)", path.display(), report.pages);
        for warning in report.warnings {
            eprintln!("warning: {warning}");
        }
    }
    Ok(())
}

fn main() -> ExitCode {
    if std::env::args().skip(1).any(|arg| arg == "--help" || arg == "-h") {
        use std::io::Write as _;
        let _ = writeln!(std::io::stdout(), "{USAGE}");
        return ExitCode::SUCCESS;
    }
    match std::panic::catch_unwind(|| options(std::env::args().skip(1)).and_then(run)) {
        Ok(Ok(())) => ExitCode::SUCCESS,
        Ok(Err(error)) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
        Err(_) => {
            eprintln!("rendering stopped unexpectedly");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invalid_scale_is_rejected() {
        for value in ["0", "-1", "NaN", "inf"] {
            let args = ["--in", "in.idml", "--png-dir", "out", "--scale", value].map(str::to_string);
            assert!(options(args).is_err(), "{value}");
        }
    }

    #[test]
    fn links_find_packaged_subfolders_and_ignore_external_symlinks() {
        let root = std::env::temp_dir().join(format!("idml-links-{}", std::process::id()));
        let nested = root.join("Links").join("nested");
        std::fs::create_dir_all(&nested).unwrap();
        std::fs::write(nested.join("image.jpg"), b"image").unwrap();
        let root = root.canonicalize().unwrap();
        assert_eq!(read_link(&root, "/old/Links/nested/image.jpg"), Some(b"image".to_vec()));
        #[cfg(unix)]
        {
            let outside = std::env::temp_dir().join(format!("idml-outside-{}", std::process::id()));
            std::fs::write(&outside, b"outside").unwrap();
            std::os::unix::fs::symlink(&outside, root.join("Links").join("outside.jpg")).unwrap();
            assert!(read_link(&root, "outside.jpg").is_none());
            std::fs::remove_file(outside).unwrap();
        }
        std::fs::remove_dir_all(root).unwrap();
    }
}
