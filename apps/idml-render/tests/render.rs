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
