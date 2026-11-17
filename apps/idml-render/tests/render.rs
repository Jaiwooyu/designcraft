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
