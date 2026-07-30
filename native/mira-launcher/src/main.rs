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

fn normalize_forwarded_args(mut args: Vec<String>) -> Vec<String> {
    if args.first().map(|arg| arg == "--").unwrap_or(false) {
        args.remove(0);
    }
    if args
        .first()
        .map(|arg| arg == "mira" || arg == "mira.exe")
        .unwrap_or(false)
    {
        args.remove(0);
    }
    args
}

fn parse_config() -> LaunchConfig {
    let mut raw_args: Vec<String> = env::args().skip(1).collect();
    let dry_run = raw_args
        .iter()
        .any(|arg| arg == "--dry-run" || arg == "doctor");
    raw_args.retain(|arg| arg != "--dry-run" && arg != "doctor");
    let forwarded_args = normalize_forwarded_args(raw_args);
    let python = env::var("MIRA_PYTHON").unwrap_or_else(|_| "python3".to_string());
    let port = parse_port(&forwarded_args);
    LaunchConfig {
        python,
        args: forwarded_args,
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

#[cfg(test)]
mod tests {
    use super::normalize_forwarded_args;

    #[test]
    fn strips_delimiter_and_cli_name_from_forwarded_args() {
        let args = vec![
            "--".to_string(),
            "mira".to_string(),
            "gateway".to_string(),
            "--config".to_string(),
            "/tmp/config.json".to_string(),
        ];
        assert_eq!(
            normalize_forwarded_args(args),
            vec!["gateway", "--config", "/tmp/config.json"]
        );
    }

    #[test]
    fn preserves_direct_subcommands() {
        let args = vec!["desktop".to_string(), "--yes".to_string()];
        assert_eq!(normalize_forwarded_args(args), vec!["desktop", "--yes"]);
    }
}

fn python_available(python: &str) -> Result<String, String> {
    let output = Command::new(python)
        .arg("--version")
        .output()
        .map_err(|error| format!("failed to execute `{python} --version`: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "`{python} --version` exited with {}",
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

fn print_doctor(config: &LaunchConfig, python_version: &str, port_free: bool) {
    let status = if port_free { "ok" } else { "port_unavailable" };
    println!(
        "{{\"status\":\"{}\",\"python\":\"{}\",\"python_version\":\"{}\",\"port\":{},\"port_available\":{},\"log_dir\":\"{}\",\"dry_run\":true}}",
        status,
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
