use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{exit, Command};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug)]
struct LaunchConfig {
    python: String,
    args: Vec<String>,
    log_dir: PathBuf,
    port: u16,
    dry_run: bool,
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
    if let Ok(home) = env::var("HOME") {
        return PathBuf::from(home)
            .join("Library")
            .join("Logs")
            .join("Mira");
    }
    env::temp_dir().join("mira-logs")
}

fn parse_port(args: &[String]) -> u16 {
    if let Ok(value) = env::var("MIRA_GATEWAY_PORT") {
        if let Ok(port) = value.parse::<u16>() {
            return port;
        }
    }
    for pair in args.windows(2) {
        if pair[0] == "--port" {
            if let Ok(port) = pair[1].parse::<u16>() {
                return port;
            }
        }
    }
    18790
}

fn parse_config() -> LaunchConfig {
    let mut raw_args: Vec<String> = env::args().skip(1).collect();
    let dry_run = raw_args.iter().any(|arg| arg == "--dry-run" || arg == "doctor");
    raw_args.retain(|arg| arg != "--dry-run");
    let python = env::var("MIRA_PYTHON").unwrap_or_else(|_| "python3".to_string());
    let port = parse_port(&raw_args);
    LaunchConfig {
        python,
        args: raw_args,
        log_dir: default_log_dir(),
        port,
        dry_run,
    }
}

fn append_log(config: &LaunchConfig, line: &str) {
    let _ = fs::create_dir_all(&config.log_dir);
    let path = config.log_dir.join("launcher.log");
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "[{}] {}", now_unix(), line);
    }
}

fn python_available(python: &str) -> Result<String, String> {
    let output = Command::new(python)
        .arg("--version")
        .output()
        .map_err(|error| format!("failed to execute `{python} --version`: {error}"))?;
    if !output.status.success() {
        return Err(format!("`{python} --version` exited with {}", output.status));
    }
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    Ok(if stdout.is_empty() { stderr } else { stdout })
}

fn port_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn print_doctor(config: &LaunchConfig, python_version: &str, port_free: bool) {
    println!(
        "{{\"status\":\"ok\",\"python\":\"{}\",\"python_version\":\"{}\",\"port\":{},\"port_available\":{},\"log_dir\":\"{}\",\"dry_run\":true}}",
        escape_json(&config.python),
        escape_json(python_version),
        config.port,
        port_free,
        escape_json(&config.log_dir.display().to_string())
    );
}

fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn main() {
    let config = parse_config();
    append_log(
        &config,
        &format!(
            "startup python={} args={:?} port={} dry_run={}",
            config.python, config.args, config.port, config.dry_run
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
    for arg in &config.args {
        command.arg(arg);
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
