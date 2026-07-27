#![forbid(unsafe_op_in_unsafe_fn)]

use std::ffi::CString;
use std::os::raw::c_char;

static READY_JSON: &str = r#"{"runtime":"mira-rust","status":"ready","abi":"c","mode":"ffi"}"#;

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
