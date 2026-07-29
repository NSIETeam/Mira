use std::env;
use std::fs;
use std::path::Path;

fn dir_size(path: &Path) -> u64 {
    let Ok(meta) = fs::symlink_metadata(path) else {
        return 0;
    };
    if meta.is_file() {
        return meta.len();
    }
    if !meta.is_dir() {
        return 0;
    }
    let Ok(entries) = fs::read_dir(path) else {
        return 0;
    };
    entries
        .filter_map(Result::ok)
        .map(|entry| dir_size(&entry.path()))
        .sum()
}

fn main() {
    let path = env::args().nth(1).unwrap_or_else(|| "dist".to_string());
    let root = Path::new(&path);
    let bytes = dir_size(root);
    println!(
        "{{\"path\":\"{}\",\"bytes\":{},\"megabytes\":{:.2}}}",
        root.display(),
        bytes,
        bytes as f64 / 1024.0 / 1024.0
    );
}
