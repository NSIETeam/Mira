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

#[derive(Debug)]
struct PackConfig {
    path: PathBuf,
    limit_mb: u64,
    json: bool,
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
    let mut top = 20usize;
    let mut doctor = false;
    let args: Vec<String> = env::args().skip(1).collect();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--json" => json = true,
            "doctor" | "--doctor" => doctor = true,
            "--limit-mb" => {
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
        top: top.clamp(1, 100),
        doctor,
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
    let bytes = children
        .filter_map(Result::ok)
        .map(|entry| dir_size(&entry.path(), entries, depth + 1))
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

fn python_status() -> String {
    let python = env::var("MIRA_PYTHON").unwrap_or_else(|_| "python3".to_string());
    match Command::new(&python).arg("--version").output() {
        Ok(output) if output.status.success() => {
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            if stdout.is_empty() { stderr } else { stdout }
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

fn print_json(config: &PackConfig, total: u64, entries: &[Entry], missing: bool) {
    let over_limit = total > config.limit_mb * 1024 * 1024;
    println!("{{");
    println!("  \"path\": \"{}\",", escape_json(&config.path.display().to_string()));
    println!("  \"exists\": {},", !missing);
    println!("  \"bytes\": {},", total);
    println!("  \"megabytes\": {:.2},", total as f64 / 1024.0 / 1024.0);
    println!("  \"limit_mb\": {},", config.limit_mb);
    println!("  \"over_limit\": {},", over_limit);
    println!("  \"python\": \"{}\",", escape_json(&python_status()));
    println!("  \"largest\": [");
    for (index, entry) in entries.iter().take(config.top).enumerate() {
        let comma = if index + 1 == entries.iter().take(config.top).count() { "" } else { "," };
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
    println!("  ]");
    println!("}}");
}

fn print_human(config: &PackConfig, total: u64, entries: &[Entry], missing: bool) {
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
        if total > config.limit_mb * 1024 * 1024 { "over limit" } else { "ok" }
    );
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

    if config.json || config.doctor {
        print_json(&config, total, &entries, missing);
    } else {
        print_human(&config, total, &entries, missing);
    }

    if missing {
        exit(2);
    }
    if total > config.limit_mb * 1024 * 1024 {
        exit(3);
    }
}
