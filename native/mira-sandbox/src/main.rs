use std::env;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{exit, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

const DEFAULT_TIMEOUT_MS: u64 = 60_000;
const DEFAULT_MAX_OUTPUT_BYTES: usize = 64 * 1024;

#[derive(Debug)]
struct Options {
    workspace: PathBuf,
    cwd: Option<PathBuf>,
    timeout_ms: u64,
    max_output_bytes: usize,
    env_pairs: Vec<(String, String)>,
    paths: Vec<PathBuf>,
    command: Vec<String>,
}

#[derive(Debug)]
struct Captured {
    text: String,
    truncated: bool,
}

fn usage() -> ! {
    eprintln!(
        "usage: mira-sandbox --workspace <path> [--cwd <path>] [--timeout-ms <n>] [--max-output-bytes <n>] [--env KEY=VALUE] [--path <path>] -- <command> [args...]"
    );
    exit(64);
}

fn json_escape(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 8);
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn emit_json(
    status: &str,
    exit_code: Option<i32>,
    stdout: &str,
    stderr: &str,
    truncated: bool,
    error: Option<&str>,
) {
    let code = exit_code.map_or("null".to_string(), |value| value.to_string());
    let error = error.map_or("null".to_string(), |value| {
        format!("\"{}\"", json_escape(value))
    });
    println!(
        "{{\"status\":\"{}\",\"exit_code\":{},\"stdout\":\"{}\",\"stderr\":\"{}\",\"truncated\":{},\"error\":{}}}",
        json_escape(status),
        code,
        json_escape(stdout),
        json_escape(stderr),
        truncated,
        error
    );
}

fn parse_args() -> Options {
    let mut args = env::args().skip(1);
    let mut workspace = None;
    let mut cwd = None;
    let mut timeout_ms = DEFAULT_TIMEOUT_MS;
    let mut max_output_bytes = DEFAULT_MAX_OUTPUT_BYTES;
    let mut env_pairs = Vec::new();
    let mut paths = Vec::new();
    let mut command = Vec::new();
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--workspace" => workspace = args.next().map(PathBuf::from),
            "--cwd" => cwd = args.next().map(PathBuf::from),
            "--timeout-ms" => {
                timeout_ms = args
                    .next()
                    .and_then(|value| value.parse().ok())
                    .unwrap_or_else(|| usage())
            }
            "--max-output-bytes" => {
                max_output_bytes = args
                    .next()
                    .and_then(|value| value.parse().ok())
                    .unwrap_or_else(|| usage())
            }
            "--env" => {
                let Some(pair) = args.next() else { usage() };
                let Some((key, value)) = pair.split_once('=') else {
                    usage()
                };
                if key.is_empty() || key.contains('\0') {
                    usage();
                }
                env_pairs.push((key.to_string(), value.to_string()));
            }
            "--path" => paths.push(args.next().map(PathBuf::from).unwrap_or_else(|| usage())),
            "--" => {
                command.extend(args);
                break;
            }
            _ => usage(),
        }
    }
    Options {
        workspace: workspace.unwrap_or_else(|| usage()),
        cwd,
        timeout_ms,
        max_output_bytes,
        env_pairs,
        paths,
        command,
    }
}

fn resolve_inside(root: &Path, raw: &Path) -> Result<PathBuf, String> {
    let joined = if raw.is_absolute() {
        raw.to_path_buf()
    } else {
        root.join(raw)
    };
    let resolved = if joined.exists() {
        joined.canonicalize().map_err(|error| error.to_string())?
    } else {
        let parent = joined.parent().unwrap_or(root);
        let parent = parent.canonicalize().map_err(|error| error.to_string())?;
        parent.join(joined.file_name().unwrap_or_default())
    };
    if resolved.starts_with(root) {
        Ok(resolved)
    } else {
        Err(format!("path escapes workspace: {}", raw.display()))
    }
}

fn read_limited<R: Read + Send + 'static>(
    mut reader: R,
    max: usize,
) -> thread::JoinHandle<Captured> {
    thread::spawn(move || {
        let mut stored = Vec::new();
        let mut truncated = false;
        let mut buf = [0_u8; 8192];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    let remaining = max.saturating_sub(stored.len());
                    if remaining > 0 {
                        stored.extend_from_slice(&buf[..n.min(remaining)]);
                    }
                    if n > remaining {
                        truncated = true;
                    }
                }
                Err(_) => break,
            }
        }
        Captured {
            text: String::from_utf8_lossy(&stored).into_owned(),
            truncated,
        }
    })
}

#[cfg(unix)]
extern "C" {
    fn setpgid(pid: i32, pgid: i32) -> i32;
    fn kill(pid: i32, sig: i32) -> i32;
}

#[cfg(unix)]
unsafe fn prepare_child(command: &mut Command) {
    use std::os::unix::process::CommandExt;
    command.pre_exec(|| {
        unsafe {
            setpgid(0, 0);
        }
        Ok(())
    });
}

#[cfg(unix)]
unsafe fn kill_process_tree(pid: u32) {
    const SIGKILL: i32 = 9;
    let _ = unsafe { kill(-(pid as i32), SIGKILL) };
}

#[cfg(not(unix))]
unsafe fn prepare_child(_command: &mut Command) {}

#[cfg(not(unix))]
unsafe fn kill_process_tree(_pid: u32) {}

fn main() {
    let options = parse_args();
    if options.command.is_empty() {
        usage();
    }
    let root = match options.workspace.canonicalize() {
        Ok(path) => path,
        Err(error) => {
            emit_json(
                "blocked",
                None,
                "",
                "",
                false,
                Some(&format!("invalid workspace: {error}")),
            );
            exit(126);
        }
    };
    let cwd = match options.cwd.as_deref() {
        Some(raw) => match resolve_inside(&root, raw) {
            Ok(path) => path,
            Err(error) => {
                emit_json("blocked", None, "", "", false, Some(&error));
                exit(126);
            }
        },
        None => root.clone(),
    };
    for path in &options.paths {
        if let Err(error) = resolve_inside(&root, path) {
            emit_json("blocked", None, "", "", false, Some(&error));
            exit(126);
        }
    }

    let mut command = Command::new(&options.command[0]);
    command
        .args(&options.command[1..])
        .current_dir(cwd)
        .env_clear()
        .env("HOME", &root)
        .env("PATH", env::var("PATH").unwrap_or_default())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    for (key, value) in options.env_pairs {
        command.env(key, value);
    }
    unsafe {
        prepare_child(&mut command);
    }
    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            emit_json(
                "process_error",
                None,
                "",
                "",
                false,
                Some(&error.to_string()),
            );
            exit(127);
        }
    };
    let stdout = read_limited(
        child.stdout.take().expect("stdout piped"),
        options.max_output_bytes,
    );
    let stderr = read_limited(
        child.stderr.take().expect("stderr piped"),
        options.max_output_bytes,
    );
    let deadline = Instant::now() + Duration::from_millis(options.timeout_ms);
    let mut timed_out = false;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if Instant::now() >= deadline => {
                timed_out = true;
                unsafe {
                    kill_process_tree(child.id());
                }
                let _ = child.kill();
                break child.wait().unwrap_or_else(|_| exit(127));
            }
            Ok(None) => thread::sleep(Duration::from_millis(10)),
            Err(error) => {
                emit_json(
                    "process_error",
                    None,
                    "",
                    "",
                    false,
                    Some(&error.to_string()),
                );
                exit(127);
            }
        }
    };
    let stdout = stdout.join().unwrap_or(Captured {
        text: String::new(),
        truncated: false,
    });
    let stderr = stderr.join().unwrap_or(Captured {
        text: String::new(),
        truncated: false,
    });
    let truncated = stdout.truncated || stderr.truncated;
    if timed_out {
        emit_json(
            "timeout",
            status.code(),
            &stdout.text,
            &stderr.text,
            truncated,
            Some("command timed out"),
        );
        exit(124);
    }
    let code = status.code().unwrap_or(1);
    emit_json(
        if code == 0 {
            "success"
        } else {
            "process_error"
        },
        Some(code),
        &stdout.text,
        &stderr.text,
        truncated,
        None,
    );
    exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root() -> PathBuf {
        let path = env::temp_dir().join(format!(
            "mira-sandbox-test-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&path).unwrap();
        path.canonicalize().unwrap()
    }

    #[test]
    fn relative_path_stays_inside_workspace() {
        let root = temp_root();
        fs::create_dir_all(root.join("subdir")).unwrap();
        assert!(resolve_inside(&root, Path::new("subdir/file.txt"))
            .unwrap()
            .starts_with(&root));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn traversal_is_blocked() {
        let root = temp_root();
        let err = resolve_inside(&root, Path::new("../outside.txt")).unwrap_err();
        assert!(err.contains("escapes workspace"));
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn symlink_escape_is_blocked() {
        use std::os::unix::fs::symlink;
        let root = temp_root();
        symlink(env::temp_dir(), root.join("link")).unwrap();
        let err = resolve_inside(&root, Path::new("link/passwd")).unwrap_err();
        assert!(err.contains("escapes workspace"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn output_is_limited() {
        let data = std::io::Cursor::new(vec![b'a'; 10]);
        let captured = read_limited(data, 4).join().unwrap();
        assert_eq!(captured.text, "aaaa");
        assert!(captured.truncated);
    }
}
