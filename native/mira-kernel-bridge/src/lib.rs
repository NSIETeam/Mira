use std::collections::{HashMap, VecDeque};
use std::ffi::CStr;
use std::os::raw::c_char;
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

const MESSAGE_CAPACITY: usize = 240;
const MODULE_CAPACITY: usize = 64;
const QUEUE_CAPACITY: usize = 512;
const COMMAND_CAPACITY: usize = 96;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct MiraKernelEvent {
    pub kind: u32,
    pub code: i32,
    pub timestamp_ms: u64,
    pub module: [u8; MODULE_CAPACITY],
    pub message: [u8; MESSAGE_CAPACITY],
}

impl MiraKernelEvent {
    fn new(kind: u32, code: i32, module: &str, message: &str) -> Self {
        Self {
            kind,
            code,
            timestamp_ms: now_ms(),
            module: encode_fixed::<MODULE_CAPACITY>(module),
            message: encode_fixed::<MESSAGE_CAPACITY>(message),
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct MiraKernelModuleState {
    pub name: [u8; MODULE_CAPACITY],
    pub status: u32,
    pub last_code: i32,
    pub updated_at_ms: u64,
}

impl MiraKernelModuleState {
    fn new(name: &str, status: u32, last_code: i32) -> Self {
        Self {
            name: encode_fixed::<MODULE_CAPACITY>(name),
            status,
            last_code,
            updated_at_ms: now_ms(),
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct MiraKernelCommand {
    pub issued_at_ms: u64,
    pub target: [u8; MODULE_CAPACITY],
    pub action: [u8; MODULE_CAPACITY],
    pub value: [u8; COMMAND_CAPACITY],
}

impl MiraKernelCommand {
    fn new(target: &str, action: &str, value: &str) -> Self {
        Self {
            issued_at_ms: now_ms(),
            target: encode_fixed::<MODULE_CAPACITY>(target),
            action: encode_fixed::<MODULE_CAPACITY>(action),
            value: encode_fixed::<COMMAND_CAPACITY>(value),
        }
    }
}

#[derive(Default)]
struct KernelBridge {
    queue: VecDeque<MiraKernelEvent>,
    commands: VecDeque<MiraKernelCommand>,
    modules: HashMap<String, MiraKernelModuleState>,
}

impl KernelBridge {
    fn push_event(&mut self, event: MiraKernelEvent) {
        if self.queue.len() >= QUEUE_CAPACITY {
            self.queue.pop_front();
        }
        self.queue.push_back(event);
    }

    fn push_command(&mut self, command: MiraKernelCommand) {
        if self.commands.len() >= QUEUE_CAPACITY {
            self.commands.pop_front();
        }
        self.commands.push_back(command);
    }
}

static BRIDGE: OnceLock<Mutex<KernelBridge>> = OnceLock::new();

fn bridge() -> &'static Mutex<KernelBridge> {
    BRIDGE.get_or_init(|| Mutex::new(KernelBridge::default()))
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn encode_fixed<const N: usize>(value: &str) -> [u8; N] {
    let mut buf = [0u8; N];
    let bytes = value.as_bytes();
    let len = bytes.len().min(N.saturating_sub(1));
    buf[..len].copy_from_slice(&bytes[..len]);
    buf
}

fn decode_ptr(value: *const c_char) -> Option<String> {
    if value.is_null() {
        return None;
    }
    let c_str = unsafe { CStr::from_ptr(value) };
    c_str.to_str().ok().map(ToOwned::to_owned)
}

#[no_mangle]
pub extern "C" fn mira_kernel_publish_event(
    kind: u32,
    code: i32,
    module: *const c_char,
    message: *const c_char,
) -> i32 {
    let Some(module_name) = decode_ptr(module) else {
        return -1;
    };
    let Some(message_text) = decode_ptr(message) else {
        return -2;
    };
    let event = MiraKernelEvent::new(kind, code, &module_name, &message_text);
    let Ok(mut state) = bridge().lock() else {
        return -3;
    };
    state.push_event(event);
    0
}

#[no_mangle]
pub extern "C" fn mira_kernel_poll_event(out_event: *mut MiraKernelEvent) -> i32 {
    if out_event.is_null() {
        return -1;
    }
    let Ok(mut state) = bridge().lock() else {
        return -2;
    };
    let Some(event) = state.queue.pop_front() else {
        return 1;
    };
    unsafe {
        *out_event = event;
    }
    0
}

#[no_mangle]
pub extern "C" fn mira_kernel_set_module_state(
    module: *const c_char,
    status: u32,
    last_code: i32,
) -> i32 {
    let Some(module_name) = decode_ptr(module) else {
        return -1;
    };
    let Ok(mut state) = bridge().lock() else {
        return -2;
    };
    let snapshot = MiraKernelModuleState::new(&module_name, status, last_code);
    state.modules.insert(module_name, snapshot);
    0
}

#[no_mangle]
pub extern "C" fn mira_kernel_read_module_state(
    module: *const c_char,
    out_state: *mut MiraKernelModuleState,
) -> i32 {
    if out_state.is_null() {
        return -1;
    }
    let Some(module_name) = decode_ptr(module) else {
        return -2;
    };
    let Ok(state) = bridge().lock() else {
        return -3;
    };
    let Some(snapshot) = state.modules.get(&module_name) else {
        return 1;
    };
    unsafe {
        *out_state = *snapshot;
    }
    0
}

#[no_mangle]
pub extern "C" fn mira_kernel_queue_depth() -> usize {
    let Ok(state) = bridge().lock() else {
        return 0;
    };
    state.queue.len()
}

#[no_mangle]
pub extern "C" fn mira_kernel_submit_command(
    target: *const c_char,
    action: *const c_char,
    value: *const c_char,
) -> i32 {
    let Some(target_name) = decode_ptr(target) else {
        return -1;
    };
    let Some(action_name) = decode_ptr(action) else {
        return -2;
    };
    let value_text = decode_ptr(value).unwrap_or_default();
    let Ok(mut state) = bridge().lock() else {
        return -3;
    };
    state.push_command(MiraKernelCommand::new(&target_name, &action_name, &value_text));
    state.modules.insert(
        target_name.clone(),
        MiraKernelModuleState::new(&target_name, 2, 0),
    );
    state.push_event(MiraKernelEvent::new(
        2,
        0,
        &target_name,
        &format!("command queued: {}", action_name),
    ));
    0
}

#[no_mangle]
pub extern "C" fn mira_kernel_poll_command(out_command: *mut MiraKernelCommand) -> i32 {
    if out_command.is_null() {
        return -1;
    }
    let Ok(mut state) = bridge().lock() else {
        return -2;
    };
    let Some(command) = state.commands.pop_front() else {
        return 1;
    };
    unsafe {
        *out_command = command;
    }
    0
}

#[no_mangle]
pub extern "C" fn mira_kernel_command_depth() -> usize {
    let Ok(state) = bridge().lock() else {
        return 0;
    };
    state.commands.len()
}
