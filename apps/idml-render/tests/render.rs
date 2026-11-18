use designcraft_doc::{CharAttrs, Document, ParaFormat, SpreadRef};
use designcraft_geom::Rect;
use std::process::Command;

#[test]
fn renders_idml_to_png_and_pdf_without_overwriting_input() {
    let root = std::env::temp_dir().join(format!("idml-render-test-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    let input = root.join("input.idml");
    let png = root.join("pages");
    let pdf = root.join("output.pdf");
    let doc = designcraft_doc::Document::new(&Default::default());
    let original = designcraft_idml::export_idml(&doc);
    std::fs::write(&input, &original).unwrap();
    let output =
        Command::new(env!("CARGO_BIN_EXE_idml-render")).arg("--in").arg(&input).arg("--png-dir").arg(&png).arg("--pdf").arg(&pdf).output().unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    assert!(std::fs::read(png.join("page-001.png")).unwrap().starts_with(b"\x89PNG\r\n\x1a\n"));
    assert!(std::fs::read(&pdf).unwrap().starts_with(b"%PDF"));
    let output = Command::new(env!("CARGO_BIN_EXE_idml-render")).arg("--in").arg(&input).arg("--pdf").arg(&input).output().unwrap();
    assert!(!output.status.success());
    assert_eq!(std::fs::read(&input).unwrap(), original);
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn analysis_preserves_source_fonts_and_does_not_change_rendering() {
    let root = std::env::temp_dir().join(format!("idml-analysis-test-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    let input = root.join("input.idml");
    let analysis = root.join("analysis.json");
    let baseline = root.join("baseline");
    let observed = root.join("observed");
    let mut doc = Document::new(&Default::default());
    let layer = doc.layers[0].id;
    doc.add_text_frame(
        SpreadRef::Doc(0),
        Rect::new(50.0, 60.0, 300.0, 300.0),
        layer,
        "Fixture headline\nFixture body.",
        ParaFormat { chars: CharAttrs { font_family: Some("Missing Fixture Font".into()), ..Default::default() }, ..Default::default() },
    )
    .unwrap();
    let original = designcraft_idml::export_idml(&doc);
    std::fs::write(&input, &original).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_idml-render"))
        .arg("--in")
        .arg(&input)
        .arg("--png-dir")
        .arg(&baseline)
        .args(["--fallback-font", "Source Serif 4"])
        .output()
        .unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    let output = Command::new(env!("CARGO_BIN_EXE_idml-render"))
        .arg("--in")
        .arg(&input)
        .arg("--png-dir")
        .arg(&observed)
        .arg("--analysis")
        .arg(&analysis)
        .args(["--fallback-font", "Source Serif 4"])
        .output()
        .unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    assert_eq!(std::fs::read(baseline.join("page-001.png")).unwrap(), std::fs::read(observed.join("page-001.png")).unwrap());
    let json: serde_json::Value = serde_json::from_slice(&std::fs::read(&analysis).unwrap()).unwrap();
    assert_eq!(json["schema_version"], 1);
    assert_eq!(json["fonts"][0]["source_family"], "Missing Fixture Font");
    assert_eq!(json["fonts"][0]["substituted_with"], "Source Serif 4");
    assert_eq!(json["candidates"][0]["status"], "needs_review");
    assert!(json["candidates"][0]["strength"].is_null());
    assert_eq!(json["pages"][0]["elements"][0]["kind"], "text");
    assert!(json["pages"][0]["elements"][0]["rendered"]["line_count"].as_u64().unwrap() > 0);
    assert_eq!(std::fs::read(&input).unwrap(), original);
    // Analysis-only mode works and refuses aliases of the source and PDF output.
    let output = Command::new(env!("CARGO_BIN_EXE_idml-render"))
        .arg("--in")
        .arg(&input)
        .arg("--analysis")
        .arg(&analysis)
        .args(["--fallback-font", "Source Serif 4"])
        .output()
        .unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    for args in [vec!["--analysis", "input.idml"], vec!["--pdf", "same.out", "--analysis", "./same.out"]] {
        let output = Command::new(env!("CARGO_BIN_EXE_idml-render")).current_dir(&root).args(["--in", "input.idml"]).args(args).output().unwrap();
        assert!(!output.status.success());
    }
    assert_eq!(std::fs::read(&input).unwrap(), original);
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn analyzes_folder_with_unicode_names_and_keeps_single_file_results() {
    let root = std::env::temp_dir().join(format!("idml-batch-test-{}", std::process::id()));
    let input = root.join("input");
    let reports = root.join("new").join("reports");
    std::fs::create_dir_all(input.join("nested")).unwrap();
    let mut doc = Document::new(&Default::default());
    let layer = doc.layers[0].id;
    doc.add_text_frame(SpreadRef::Doc(0), Rect::new(50.0, 60.0, 300.0, 300.0), layer, "Batch fixture", ParaFormat::default()).unwrap();
    let original = designcraft_idml::export_idml(&doc);
    for name in ["1면.idml", "2면.IDML"] {
        std::fs::write(input.join(name), &original).unwrap();
    }
    std::fs::write(input.join("readme.txt"), b"not an IDML file").unwrap();
    std::fs::write(input.join("nested").join("ignored.idml"), b"invalid nested input").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_idml-render"))
        .arg("--in-dir")
        .arg(&input)
        .arg("--analysis-dir")
        .arg(&reports)
        .args(["--fallback-font", "Source Serif 4"])
        .output()
        .unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    assert!(String::from_utf8_lossy(&output.stderr).contains("2 succeeded, 0 failed, 2 total"));
    assert_eq!(std::fs::read_dir(&reports).unwrap().count(), 2);
    let baseline = root.join("single.json");
    let output = Command::new(env!("CARGO_BIN_EXE_idml-render"))
        .arg("--in")
        .arg(input.join("1면.idml"))
        .arg("--analysis")
        .arg(&baseline)
        .args(["--fallback-font", "Source Serif 4"])
        .output()
        .unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    for (source, report) in [("1면.idml", "1면.json"), ("2면.IDML", "2면.json")] {
        assert_eq!(std::fs::read(reports.join(report)).unwrap(), std::fs::read(&baseline).unwrap());
        assert_eq!(std::fs::read(input.join(source)).unwrap(), original);
    }
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn folder_analysis_continues_after_failure_and_preserves_existing_report() {
    let root = std::env::temp_dir().join(format!("idml-batch-failure-test-{}", std::process::id()));
    let input = root.join("input");
    let reports = root.join("reports");
    std::fs::create_dir_all(&input).unwrap();
    std::fs::create_dir_all(&reports).unwrap();
    std::fs::write(input.join("a-broken.idml"), b"not a ZIP").unwrap();
    std::fs::write(reports.join("a-broken.json"), b"previous report").unwrap();
    let original = designcraft_idml::export_idml(&Document::new(&Default::default()));
    std::fs::write(input.join("z-valid.idml"), &original).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_idml-render")).arg("--in-dir").arg(&input).arg("--analysis-dir").arg(&reports).output().unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("a-broken.idml"), "{stderr}");
    assert!(stderr.contains("1 succeeded, 1 failed, 2 total"), "{stderr}");
    assert_eq!(std::fs::read(reports.join("a-broken.json")).unwrap(), b"previous report");
    let report: serde_json::Value = serde_json::from_slice(&std::fs::read(reports.join("z-valid.json")).unwrap()).unwrap();
    assert_eq!(report["schema_version"], 1);
    assert_eq!(std::fs::read(input.join("z-valid.idml")).unwrap(), original);
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn folder_analysis_rejects_empty_and_oversized_batches() {
    let root = std::env::temp_dir().join(format!("idml-batch-limits-test-{}", std::process::id()));
    let input = root.join("input");
    let reports = root.join("reports");
    std::fs::create_dir_all(&input).unwrap();
    for expected in ["no IDML files found", "directory exceeds 1000 IDML files"] {
        let output =
            Command::new(env!("CARGO_BIN_EXE_idml-render")).arg("--in-dir").arg(&input).arg("--analysis-dir").arg(&reports).output().unwrap();
        assert!(!output.status.success());
        assert!(String::from_utf8_lossy(&output.stderr).contains(expected), "{}", String::from_utf8_lossy(&output.stderr));
        assert!(!reports.exists());
        if expected == "no IDML files found" {
            for index in 0..1_001 {
                std::fs::write(input.join(format!("{index}.idml")), b"").unwrap();
            }
        }
    }
    std::fs::remove_dir_all(root).unwrap();
}
