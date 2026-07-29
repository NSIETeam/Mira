use std::env;
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{exit, Command};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug)]
struct LaunchConfig {
    python: PathBuf,
    args: Vec<OsString>,
    log_dir: PathBuf,
    port: u16,
    dry_run: bool,
    package_root: Option<PathBuf>,
    config_path: Option<PathBuf>,
}

fn usage() -> ! {
    eprintln!("usage: mira-launcher [--python <path>] [--package-root <path>] [--config <path>] [--dry-run|doctor] [--] [mira] <args...>");
    exit(64);
}

fn now_unix() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

fn default_log_dir() -> PathBuf {
    if let Ok(value) = env::var("MIRA_LOG_DIR") {
        return PathBuf::from(value);
    }
    if cfg!(target_os = "windows") {
        if let Ok(root) = env::var("LOCALAPPDATA") {
            return PathBuf::from(root).join("Mira").join("Logs");
        }
        if let Ok(home) = env::var("USERPROFILE") {
            return PathBuf::from(home)
                .join("AppData")
                .join("Local")
                .join("Mira")
                .join("Logs");
        }
    }
    if cfg!(target_os = "macos") {
        if let Ok(home) = env::var("HOME") {
            return PathBuf::from(home)
                .join("Library")
                .join("Logs")
                .join("Mira");
        }
    }
    if let Ok(root) = env::var("XDG_STATE_HOME") {
        return PathBuf::from(root).join("mira").join("logs");
    }
    if let Ok(home) = env::var("HOME") {
        return PathBuf::from(home)
            .join(".local")
            .join("state")
            .join("mira")
            .join("logs");
    }
    env::temp_dir().join("mira-logs")
}

fn candidate_pythons(explicit: Option<PathBuf>) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Some(path) = explicit {
        out.push(path);
    }
    if let Ok(value) = env::var("MIRA_PYTHON") {
        out.push(PathBuf::from(value));
    }
    if let Ok(exe) = env::current_exe() {
        if let Some(dir) = exe.parent() {
            out.extend([
                dir.join("python").join("bin").join("python3"),
                dir.join("python").join("python.exe"),
                dir.join("runtime").join("python").join("python.exe"),
                dir.join("runtime")
                    .join("python")
                    .join("bin")
                    .join("python3"),
            ]);
        }
    }
    out.push(PathBuf::from("python3"));
    out.push(PathBuf::from("python"));
    out
}

fn resolve_python(explicit: Option<PathBuf>) -> PathBuf {
    for path in candidate_pythons(explicit) {
        if path.components().count() == 1 || path.exists() {
            return path;
        }
    }
    PathBuf::from("python3")
}

fn parse_port(args: &[OsString]) -> u16 {
    if let Ok(value) = env::var("MIRA_GATEWAY_PORT") {
        if let Ok(port) = value.parse::<u16>() {
            return port;
        }
    }
    for pair in args.windows(2) {
        if pair[0] == "--port" {
            if let Some(value) = pair[1].to_str() {
                if let Ok(port) = value.parse::<u16>() {
                    return port;
                }
            }
        }
    }
    18790
}

fn parse_config() -> LaunchConfig {
    let mut explicit_python = None;
    let mut package_root = None;
    let mut config_path = None;
    let mut dry_run = false;
    let mut command_args = Vec::new();
    let mut args = env::args_os().skip(1).peekable();
    while let Some(arg) = args.next() {
        if arg == "--" {
            command_args.extend(args);
            break;
        }
        if arg == "--python" {
            explicit_python = args.next().map(PathBuf::from);
            if explicit_python.is_none() {
                usage();
            }
            continue;
        }
        if arg == "--package-root" {
            package_root = args.next().map(PathBuf::from);
            if package_root.is_none() {
                usage();
            }
            continue;
        }
        if arg == "--config" {
            let Some(path) = args.next().map(PathBuf::from) else {
                usage();
            };
            command_args.push(OsString::from("--config"));
            command_args.push(path.as_os_str().to_os_string());
            config_path = Some(path);
            continue;
        }
        if arg == "--dry-run" || arg == "doctor" {
            dry_run = true;
            continue;
        }
        command_args.push(arg);
        command_args.extend(args);
        break;
    }
    if command_args.first().map_or(false, |arg| arg == "mira") {
        command_args.remove(0);
    }
    if command_args.is_empty() {
        command_args.push(OsString::from("gateway"));
    }
    let port = parse_port(&command_args);
    LaunchConfig {
        python: resolve_python(explicit_python),
        args: command_args,
        log_dir: default_log_dir(),
        port,
        dry_run,
        package_root,
        config_path,
    }
}

fn append_log(config: &LaunchConfig, line: &str) {
    let _ = fs::create_dir_all(&config.log_dir);
    let path = config.log_dir.join("launcher.log");
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "[{}] {}", now_unix(), line);
    }
}

fn python_available(python: &Path) -> Result<String, String> {
    let output = Command::new(python)
        .arg("--version")
        .output()
        .map_err(|error| {
            format!(
                "failed to execute `{}` --version: {error}",
                python.display()
            )
        })?;
    if !output.status.success() {
        return Err(format!(
            "`{} --version` exited with {}",
            python.display(),
            output.status
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    Ok(if stdout.is_empty() { stderr } else { stdout })
}

fn port_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn print_doctor(config: &LaunchConfig, python_version: &str, port_free: bool) {
    let status = if port_free { "ok" } else { "port_unavailable" };
    println!(
        "{{\"status\":\"{}\",\"python\":\"{}\",\"python_version\":\"{}\",\"port\":{},\"port_available\":{},\"log_dir\":\"{}\",\"package_root\":{},\"config\":{},\"dry_run\":true}}",
        status,
        escape_json(&config.python.display().to_string()),
        escape_json(python_version),
        config.port,
        port_free,
        escape_json(&config.log_dir.display().to_string()),
        config
            .package_root
            .as_ref()
            .map(|path| format!("\"{}\"", escape_json(&path.display().to_string())))
            .unwrap_or_else(|| "null".to_string()),
        config
            .config_path
            .as_ref()
            .map(|path| format!("\"{}\"", escape_json(&path.display().to_string())))
            .unwrap_or_else(|| "null".to_string())
    );
}

fn validate_path(label: &str, path: &Path) {
    if !path.exists() {
        eprintln!("mira-launcher: {label} does not exist: {}", path.display());
        exit(66);
    }
}

fn main() {
    let config = parse_config();
    if let Some(path) = config.package_root.as_deref() {
        validate_path("package root", path);
    }
    if let Some(path) = config.config_path.as_deref() {
        validate_path("config", path);
    }
    append_log(
        &config,
        &format!(
            "startup python={} args={:?} port={} dry_run={}",
            config.python.display(),
            config.args,
            config.port,
            config.dry_run
        ),
    );

    let python_version = match python_available(&config.python) {
        Ok(version) => version,
        Err(error) => {
            append_log(&config, &format!("error {error}"));
            eprintln!("mira-launcher: {error}");
            exit(127);
        }
    };
    let port_free = port_available(config.port);
    append_log(
        &config,
        &format!("doctor python_version={python_version:?} port_available={port_free}"),
    );

    if config.dry_run {
        print_doctor(&config, &python_version, port_free);
        exit(if port_free { 0 } else { 2 });
    }

    let mut command = Command::new(&config.python);
    command.arg("-m").arg("mira.cli.commands");
    command.args(&config.args);
    if let Some(path) = config.package_root.as_deref() {
        command.current_dir(path);
    }
    match command.status() {
        Ok(status) => {
            append_log(&config, &format!("exit status={status}"));
            exit(status.code().unwrap_or(1));
        }
        Err(error) => {
            append_log(&config, &format!("spawn_error {error}"));
            eprintln!("mira-launcher: failed to start Mira Python runtime: {error}");
            exit(127);
        }
    }
}
