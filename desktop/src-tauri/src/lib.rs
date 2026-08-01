use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct LocalService(Mutex<Option<CommandChild>>);

fn service_args() -> Vec<&'static str> {
    vec!["--port", "8765"]
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let mut child = None;
            for attempt in 1..=3 {
                child = app
                    .shell()
                    .sidecar("crypto-signal-service")
                    .ok()
                    .and_then(|command| command.args(service_args()).spawn().ok())
                    .map(|(_events, child)| child);
                if child.is_some() {
                    break;
                }
                eprintln!("local service failed to start (attempt {attempt}/3)");
                std::thread::sleep(std::time::Duration::from_millis(250 * attempt));
            }
            app.manage(LocalService(Mutex::new(child)));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build Crypto Signal Terminal");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            let state = app_handle.state::<LocalService>();
            if let Ok(mut slot) = state.0.lock() {
                if let Some(child) = slot.take() {
                    let _ = child.kill();
                }
            };
        }
    });
}

#[cfg(test)]
mod tests {
    #[test]
    fn local_service_never_receives_secrets_on_command_line() {
        let args = super::service_args();
        assert_eq!(args, vec!["--port", "8765"]);
        assert!(!args.join(" ").to_lowercase().contains("token"));
        assert!(!args.join(" ").to_lowercase().contains("hash"));
    }
}
