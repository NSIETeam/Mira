#![forbid(unsafe_op_in_unsafe_fn)]

use std::ffi::CString;
use std::os::raw::c_char;

static READY_JSON: &str = r#"{"runtime":"mira-rust","status":"ready","abi":"c","mode":"ffi","kernel_surface":"mira","version":"0.1.0","queue_depth":0,"module_count":2,"capabilities":["task_exec","fault_stream","module_state","diagnostics","hot_swap_ready"],"module_states":{"scheduler":{"status":"ready","last_code":0},"dispatch":{"status":"ready","last_code":0}}}"#;

#[no_mangle]
pub extern "C" fn mira_runtime_status_json() -> *mut c_char {
    CString::new(READY_JSON)
        .expect("static JSON is valid")
        .into_raw()
}

#[no_mangle]
pub extern "C" fn mira_runtime_free_json(ptr: *mut c_char) {
    if ptr.is_null() {
        return;
    }
    unsafe {
        drop(CString::from_raw(ptr));
    }
}
