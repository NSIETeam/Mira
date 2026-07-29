use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{exit, Command};

#[derive(Clone, Debug)]
struct Entry {
    path: PathBuf,
    bytes: u64,
    is_dir: bool,
}

#[derive(Clone, Debug)]
struct Category {
    name: &'static str,
    bytes: u64,
}

#[derive(Debug)]
struct PackConfig {
    path: PathBuf,
    limit_mb: u64,
    json: bool,
    table: bool,
    top: usize,
    doctor: bool,
}

fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn parse_config() -> PackConfig {
    let mut path = PathBuf::from("dist");
    let mut limit_mb = env::var("MIRA_PACK_LIMIT_MB")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(180);
    let mut json = false;
    let mut table = false;
    let mut top = 20usize;
    let mut doctor = false;
    let args: Vec<String> = env::args().skip(1).collect();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--json" => json = true,
            "--format" => {
                if let Some(value) = args.get(index + 1) {
                    json = value == "json";
                    table = value == "table";
                    index += 1;
                }
            }
            "doctor" | "--doctor" => doctor = true,
            "--limit-mb" | "--budget-mb" => {
                if let Some(value) = args.get(index + 1) {
                    if let Ok(parsed) = value.parse() {
                        limit_mb = parsed;
                    }
                    index += 1;
                }
            }
            "--top" => {
                if let Some(value) = args.get(index + 1) {
                    if let Ok(parsed) = value.parse() {
                        top = parsed;
                    }
                    index += 1;
                }
            }
            value if !value.starts_with('-') => path = PathBuf::from(value),
            _ => {}
        }
        index += 1;
    }
    PackConfig {
        path,
        limit_mb,
        json,
        table,
        top: top.clamp(1, 100),
        doctor,
    }
}

fn classify(path: &Path) -> &'static str {
    let lower = path
        .display()
        .to_string()
        .replace('\\', "/")
        .to_ascii_lowercase();
    if lower.contains("site-packages") || lower.contains("python") || lower.ends_with(".pyc") {
        "python-runtime"
    } else if lower.contains("webui")
        || lower.contains("assets")
        || lower.ends_with(".js")
        || lower.ends_with(".css")
    {
        "webui-assets"
    } else if lower.ends_with(".exe")
        || lower.ends_with(".dll")
        || lower.ends_with(".dylib")
        || lower.ends_with(".so")
        || lower.contains("mira-launcher")
        || lower.contains("mira-sandbox")
    {
        "native-binaries"
    } else if lower.contains("model") || lower.contains("cache") {
        "models-cache"
    } else if lower.contains("doc") || lower.ends_with(".md") || lower.ends_with(".txt") {
        "docs-examples"
    } else {
        "other"
    }
}

fn dir_size(path: &Path, entries: &mut Vec<Entry>, depth: usize) -> u64 {
    let Ok(meta) = fs::symlink_metadata(path) else {
        return 0;
    };
    if meta.is_file() {
        let bytes = meta.len();
        entries.push(Entry {
            path: path.to_path_buf(),
            bytes,
            is_dir: false,
        });
        return bytes;
    }
    if !meta.is_dir() {
        return 0;
    }
    let Ok(children) = fs::read_dir(path) else {
        return 0;
    };
    let mut child_paths: Vec<PathBuf> = children
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .collect();
    child_paths.sort();
    let bytes = child_paths
        .iter()
        .map(|child| dir_size(child, entries, depth + 1))
        .sum();
    if depth <= 2 {
        entries.push(Entry {
            path: path.to_path_buf(),
            bytes,
            is_dir: true,
        });
    }
    bytes
}

fn categories(entries: &[Entry]) -> Vec<Category> {
    let names = [
        "python-runtime",
        "webui-assets",
        "native-binaries",
        "models-cache",
        "docs-examples",
        "other",
    ];
    let mut out: Vec<Category> = names
        .iter()
        .map(|name| Category { name, bytes: 0 })
        .collect();
    for entry in entries.iter().filter(|entry| !entry.is_dir) {
        let name = classify(&entry.path);
        if let Some(row) = out.iter_mut().find(|row| row.name == name) {
            row.bytes += entry.bytes;
        }
    }
    out
}

fn python_status() -> String {
    let python = env::var("MIRA_PYTHON").unwrap_or_else(|_| "python3".to_string());
    match Command::new(&python).arg("--version").output() {
        Ok(output) if output.status.success() => {
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            if stdout.is_empty() {
                stderr
            } else {
                stdout
            }
        }
        Ok(output) => format!("{python} exited with {status}", status = output.status),
        Err(error) => format!("{python} unavailable: {error}"),
    }
}

fn trim_hint(path: &Path) -> &'static str {
    let text = path.display().to_string().to_lowercase();
    if text.contains("node_modules") {
        "review bundled node_modules"
    } else if text.contains("__pycache__") || text.ends_with(".pyc") {
        "remove python cache"
    } else if text.contains(".map") {
        "omit sourcemaps from release"
    } else if text.contains("test") || text.contains("fixture") {
        "exclude tests and fixtures"
    } else if text.contains("electron") || text.contains("chromium") {
        "check electron/chromium payload"
    } else {
        "inspect payload necessity"
    }
}

fn print_json(
    config: &PackConfig,
    total: u64,
    entries: &[Entry],
    categories: &[Category],
    missing: bool,
) {
    let limit_bytes = config.limit_mb * 1024 * 1024;
    let over_limit = total > limit_bytes;
    println!("{{");
    println!(
        "  \"path\": \"{}\",",
        escape_json(&config.path.display().to_string())
    );
    println!("  \"exists\": {},", !missing);
    println!("  \"bytes\": {},", total);
    println!("  \"total_bytes\": {},", total);
    println!("  \"megabytes\": {:.2},", total as f64 / 1024.0 / 1024.0);
    println!("  \"limit_mb\": {},", config.limit_mb);
    println!("  \"budget_bytes\": {},", limit_bytes);
    println!("  \"over_limit\": {},", over_limit);
    println!("  \"over_budget\": {},", over_limit);
    println!("  \"python\": \"{}\",", escape_json(&python_status()));
    println!("  \"categories\": [");
    for (index, row) in categories.iter().enumerate() {
        let comma = if index + 1 == categories.len() {
            ""
        } else {
            ","
        };
        println!(
            "    {{\"name\":\"{}\",\"bytes\":{}}}{}",
            row.name, row.bytes, comma
        );
    }
    println!("  ],");
    println!("  \"largest\": [");
    let shown = entries.iter().take(config.top).count();
    for (index, entry) in entries.iter().take(config.top).enumerate() {
        let comma = if index + 1 == shown { "" } else { "," };
        println!(
            "    {{\"path\":\"{}\",\"bytes\":{},\"megabytes\":{:.2},\"kind\":\"{}\",\"hint\":\"{}\"}}{}",
            escape_json(&entry.path.display().to_string()),
            entry.bytes,
            entry.bytes as f64 / 1024.0 / 1024.0,
            if entry.is_dir { "dir" } else { "file" },
            trim_hint(&entry.path),
            comma
        );
    }
    println!("  ],");
    println!("  \"top_offenders\": [");
    let files: Vec<&Entry> = entries
        .iter()
        .filter(|entry| !entry.is_dir)
        .take(config.top)
        .collect();
    for (index, entry) in files.iter().enumerate() {
        let comma = if index + 1 == files.len() { "" } else { "," };
        println!(
            "    {{\"path\":\"{}\",\"bytes\":{}}}{}",
            escape_json(&entry.path.display().to_string()),
            entry.bytes,
            comma
        );
    }
    println!("  ]");
    println!("}}");
}

fn print_human(
    config: &PackConfig,
    total: u64,
    entries: &[Entry],
    categories: &[Category],
    missing: bool,
) {
    println!("Mira package audit");
    println!("path: {}", config.path.display());
    println!("exists: {}", !missing);
    println!("size: {:.2} MB", total as f64 / 1024.0 / 1024.0);
    println!("limit: {} MB", config.limit_mb);
    println!("python: {}", python_status());
    if missing {
        println!("status: missing input path");
        return;
    }
    println!(
        "status: {}",
        if total > config.limit_mb * 1024 * 1024 {
            "over limit"
        } else {
            "ok"
        }
    );
    println!("categories:");
    for category in categories {
        println!(
            "- {}: {:.2} MB",
            category.name,
            category.bytes as f64 / 1024.0 / 1024.0
        );
    }
    println!("largest:");
    for entry in entries.iter().take(config.top) {
        println!(
            "- {:.2} MB {} [{}] - {}",
            entry.bytes as f64 / 1024.0 / 1024.0,
            entry.path.display(),
            if entry.is_dir { "dir" } else { "file" },
            trim_hint(&entry.path)
        );
    }
}

fn print_table(total: u64, categories: &[Category], entries: &[Entry], top: usize) {
    println!(
        "Total: {} bytes ({:.2} MiB)",
        total,
        total as f64 / 1024.0 / 1024.0
    );
    println!("\nCategory                 Bytes");
    for row in categories {
        println!("{:<22} {}", row.name, row.bytes);
    }
    println!("\nTop offenders");
    for row in entries.iter().filter(|entry| !entry.is_dir).take(top) {
        println!("{:<10} {}", row.bytes, row.path.display());
    }
}

fn main() {
    let config = parse_config();
    let missing = !config.path.exists();
    let mut entries = Vec::new();
    let total = if missing {
        0
    } else {
        dir_size(&config.path, &mut entries, 0)
    };
    entries.sort_by(|a, b| b.bytes.cmp(&a.bytes).then_with(|| a.path.cmp(&b.path)));
    let category_rows = categories(&entries);

    if config.json || config.doctor {
        print_json(&config, total, &entries, &category_rows, missing);
    } else if config.table {
        print_table(total, &category_rows, &entries, config.top);
    } else {
        print_human(&config, total, &entries, &category_rows, missing);
    }

    if missing {
        exit(2);
    }
    if total > config.limit_mb * 1024 * 1024 {
        exit(3);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root() -> PathBuf {
        let path = env::temp_dir().join(format!(
            "mira-pack-test-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[test]
    fn classifies_expected_groups() {
        assert_eq!(
            classify(Path::new("Python/site-packages/a.py")),
            "python-runtime"
        );
        assert_eq!(classify(Path::new("webui/assets/app.js")), "webui-assets");
        assert_eq!(classify(Path::new("bin/mira-launcher")), "native-binaries");
        assert_eq!(classify(Path::new("docs/readme.md")), "docs-examples");
    }

    #[test]
    fn walks_fixture_sizes() {
        let root = temp_root();
        fs::create_dir_all(root.join("webui/assets")).unwrap();
        fs::write(root.join("webui/assets/app.js"), b"12345").unwrap();
        let mut entries = Vec::new();
        assert_eq!(dir_size(&root, &mut entries, 0), 5);
        assert!(entries.iter().any(|entry| entry.bytes == 5));
        let _ = fs::remove_dir_all(root);
    }
}
