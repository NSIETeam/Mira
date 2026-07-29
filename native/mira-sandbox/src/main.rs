use std::env;
use std::path::{Path, PathBuf};
use std::process::{exit, Command};

fn usage() -> ! {
    eprintln!("usage: mira-sandbox --workspace <path> -- <command> [args...]");
    exit(64);
}

fn canonical_or_join(workspace: &Path, raw: &str) -> PathBuf {
    let path = PathBuf::from(raw);
    if path.is_absolute() {
        path
    } else {
        workspace.join(path)
    }
}

fn main() {
    let mut args = env::args().skip(1);
    let mut workspace: Option<PathBuf> = None;
    let mut command: Vec<String> = Vec::new();
    while let Some(arg) = args.next() {
        if arg == "--workspace" {
            workspace = args.next().map(PathBuf::from);
            continue;
        }
        if arg == "--" {
            command.extend(args);
            break;
        }
        usage();
    }
    let Some(workspace) = workspace else { usage() };
    if command.is_empty() {
        usage();
    }
    let root = workspace.canonicalize().unwrap_or(workspace);
    let cwd = env::current_dir().unwrap_or_else(|_| root.clone());
    let resolved_cwd = canonical_or_join(&root, cwd.to_string_lossy().as_ref());
    if !resolved_cwd.starts_with(&root) {
        eprintln!("mira-sandbox: current directory is outside workspace");
        exit(126);
    }
    let status = Command::new(&command[0])
        .args(&command[1..])
        .current_dir(root)
        .status();
    match status {
        Ok(status) => exit(status.code().unwrap_or(1)),
        Err(error) => {
            eprintln!("mira-sandbox: failed to execute command: {error}");
            exit(127);
        }
    }
}
