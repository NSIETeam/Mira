use std::env;
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::{exit, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Debug)]
struct SandboxConfig {
    workspace: PathBuf,
    command: Vec<String>,
    timeout_ms: u64,
    max_output_bytes: usize,
    json: bool,
}

#[derive(Debug)]
struct RunResult {
    status: &'static str,
    exit_code: i32,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    reason: String,
}

fn usage() -> ! {
    eprintln!(
        "usage: mira-sandbox --workspace <path> [--timeout-ms n] [--max-output-bytes n] [--json] -- <command> [args...]"
    );
    exit(64);
}

fn parse_config() -> SandboxConfig {
    let mut args = env::args().skip(1);
    let mut workspace: Option<PathBuf> = None;
    let mut timeout_ms = 30_000_u64;
    let mut max_output_bytes = 128 * 1024_usize;
    let mut json = false;
    let mut command: Vec<String> = Vec::new();
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--workspace" => workspace = args.next().map(PathBuf::from),
            "--timeout-ms" => {
                if let Some(value) = args.next() {
                    timeout_ms = value.parse().unwrap_or(timeout_ms);
                }
            }
            "--max-output-bytes" => {
                if let Some(value) = args.next() {
                    max_output_bytes = value.parse().unwrap_or(max_output_bytes);
                }
            }
            "--json" => json = true,
            "--" => {
                command.extend(args);
                break;
            }
            _ => usage(),
        }
    }
    let Some(workspace) = workspace else { usage() };
    if command.is_empty() {
        usage();
    }
    SandboxConfig {
        workspace,
        command,
        timeout_ms: timeout_ms.clamp(1, 3_600_000),
        max_output_bytes: max_output_bytes.clamp(1, 8 * 1024 * 1024),
        json,
    }
}

fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn truncate(mut bytes: Vec<u8>, max: usize) -> Vec<u8> {
    if bytes.len() > max {
        bytes.truncate(max);
    }
    bytes
}

fn is_path_like(value: &str) -> bool {
    value.contains('/') || value.contains('\\') || value == "." || value == ".."
}

fn lexical_escape(path: &Path) -> bool {
    let mut depth = 0_i32;
    for component in path.components() {
        match component {
            Component::ParentDir => {
                depth -= 1;
                if depth < 0 {
                    return true;
                }
            }
            Component::Normal(_) => depth += 1,
            Component::CurDir => {}
            Component::RootDir | Component::Prefix(_) => return false,
        }
    }
    false
}

fn resolve_candidate(root: &Path, raw: &str) -> PathBuf {
    let path = PathBuf::from(raw);
    if path.is_absolute() {
        path
    } else {
        root.join(path)
    }
}

fn within(root: &Path, path: &Path) -> bool {
    path.starts_with(root)
}

fn validate_values(root: &Path, values: &[String]) -> Result<(), String> {
    for value in values {
        if !is_path_like(value) || value.starts_with('-') {
            continue;
        }
        let raw_path = PathBuf::from(value);
        if raw_path.is_relative() && lexical_escape(&raw_path) {
            return Err(format!("path escapes workspace: {value}"));
        }
        let candidate = resolve_candidate(root, value);
        if !within(root, &candidate) {
            return Err(format!("path outside workspace: {value}"));
        }
        if candidate.exists() {
            let resolved = fs::canonicalize(&candidate)
                .map_err(|error| format!("cannot resolve path {value}: {error}"))?;
            if !within(root, &resolved) {
                return Err(format!("symlink escapes workspace: {value}"));
            }
        }
    }
    Ok(())
}

fn validate_workspace_paths(root: &Path, command: &[String]) -> Result<(), String> {
    validate_values(root, command)?;
    if command.len() >= 3 && command[0] == "sh" && command[1] == "-c" {
        let shell_tokens: Vec<String> = command[2]
            .split_whitespace()
            .map(|token| {
                token
                    .trim_matches(|ch: char| matches!(ch, '\'' | '"' | ';' | '&' | '|' | '(' | ')'))
            })
            .filter(|token| !token.is_empty())
            .map(str::to_string)
            .collect();
        validate_values(root, &shell_tokens)?;
    }
    Ok(())
}

fn read_pipe<T: Read + Send + 'static>(mut pipe: T) -> thread::JoinHandle<Vec<u8>> {
    thread::spawn(move || {
        let mut output = Vec::new();
        let _ = pipe.read_to_end(&mut output);
        output
    })
}

fn run(config: &SandboxConfig, root: &Path) -> RunResult {
    if let Err(reason) = validate_workspace_paths(root, &config.command) {
        return RunResult {
            status: "blocked",
            exit_code: 126,
            stdout: Vec::new(),
            stderr: Vec::new(),
            reason,
        };
    }

    let mut child = match Command::new(&config.command[0])
        .args(&config.command[1..])
        .current_dir(root)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => child,
        Err(error) => {
            return RunResult {
                status: "process_error",
                exit_code: 127,
                stdout: Vec::new(),
                stderr: Vec::new(),
                reason: format!("failed to execute command: {error}"),
            }
        }
    };

    let stdout = child.stdout.take().map(read_pipe);
    let stderr = child.stderr.take().map(read_pipe);
    let deadline = Instant::now() + Duration::from_millis(config.timeout_ms);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) => {
                if Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    break Err("timeout");
                }
                thread::sleep(Duration::from_millis(20));
            }
            Err(_) => break Err("wait_error"),
        }
    };
    let stdout = stdout
        .and_then(|handle| handle.join().ok())
        .map(|bytes| truncate(bytes, config.max_output_bytes))
        .unwrap_or_default();
    let stderr = stderr
        .and_then(|handle| handle.join().ok())
        .map(|bytes| truncate(bytes, config.max_output_bytes))
        .unwrap_or_default();

    match status {
        Ok(status) => RunResult {
            status: "ok",
            exit_code: status.code().unwrap_or(1),
            stdout,
            stderr,
            reason: String::new(),
        },
        Err("timeout") => RunResult {
            status: "timeout",
            exit_code: 124,
            stdout,
            stderr,
            reason: format!("command exceeded {}ms", config.timeout_ms),
        },
        Err(reason) => RunResult {
            status: "process_error",
            exit_code: 127,
            stdout,
            stderr,
            reason: reason.to_string(),
        },
    }
}

fn print_json(result: &RunResult) {
    println!("{{");
    println!("  \"status\": \"{}\",", result.status);
    println!("  \"exit_code\": {},", result.exit_code);
    println!(
        "  \"stdout\": \"{}\",",
        escape_json(&String::from_utf8_lossy(&result.stdout))
    );
    println!(
        "  \"stderr\": \"{}\",",
        escape_json(&String::from_utf8_lossy(&result.stderr))
    );
    println!("  \"reason\": \"{}\"", escape_json(&result.reason));
    println!("}}");
}

fn main() {
    let config = parse_config();
    let root = match fs::canonicalize(&config.workspace) {
        Ok(root) => root,
        Err(error) => {
            eprintln!("mira-sandbox: workspace could not be resolved: {error}");
            exit(126);
        }
    };
    let result = run(&config, &root);
    if config.json {
        print_json(&result);
    } else {
        print!("{}", String::from_utf8_lossy(&result.stdout));
        eprint!("{}", String::from_utf8_lossy(&result.stderr));
        if !result.reason.is_empty() {
            eprintln!("mira-sandbox: {}", result.reason);
        }
    }
    exit(result.exit_code);
}

#[cfg(test)]
mod tests {
    use super::{validate_workspace_paths, SandboxConfig};
    use std::fs;

    #[test]
    fn blocks_parent_path_escape() {
        let root = std::env::temp_dir().join("mira-sandbox-test-root");
        let _ = fs::create_dir_all(&root);
        let command = vec!["cat".to_string(), "../secret".to_string()];
        assert!(validate_workspace_paths(&root, &command).is_err());
    }

    #[test]
    fn allows_bare_shell_command() {
        let root = std::env::temp_dir().join("mira-sandbox-test-root");
        let _ = fs::create_dir_all(&root);
        let command = vec!["sh".to_string(), "-c".to_string(), "echo ok".to_string()];
        assert!(validate_workspace_paths(&root, &command).is_ok());
    }

    #[test]
    fn blocks_shell_string_path_escape() {
        let root = std::env::temp_dir().join("mira-sandbox-test-root");
        let _ = fs::create_dir_all(&root);
        let command = vec![
            "sh".to_string(),
            "-c".to_string(),
            "cat ../secret".to_string(),
        ];
        assert!(validate_workspace_paths(&root, &command).is_err());
    }

    #[test]
    fn clamps_runtime_limits() {
        let config = SandboxConfig {
            workspace: ".".into(),
            command: vec!["true".to_string()],
            timeout_ms: 1,
            max_output_bytes: 1,
            json: true,
        };
        assert_eq!(config.timeout_ms, 1);
        assert_eq!(config.max_output_bytes, 1);
    }
}
