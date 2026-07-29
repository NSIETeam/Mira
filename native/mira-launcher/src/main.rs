use std::env;
use std::process::{exit, Command};

fn main() {
    let python = env::var("MIRA_PYTHON").unwrap_or_else(|_| "python3".to_string());
    let mut command = Command::new(python);
    command.arg("-m").arg("mira.cli.commands");
    for arg in env::args().skip(1) {
        command.arg(arg);
    }
    match command.status() {
        Ok(status) => exit(status.code().unwrap_or(1)),
        Err(error) => {
            eprintln!("mira-launcher: failed to start Mira Python runtime: {error}");
            exit(127);
        }
    }
}
