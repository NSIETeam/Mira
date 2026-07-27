#ifndef MIRA_KERNEL_BRIDGE_H
#define MIRA_KERNEL_BRIDGE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MIRA_KERNEL_MODULE_CAPACITY 64
#define MIRA_KERNEL_MESSAGE_CAPACITY 240

typedef struct MiraKernelEvent {
  uint32_t kind;
  int32_t code;
  uint64_t timestamp_ms;
  uint8_t module[MIRA_KERNEL_MODULE_CAPACITY];
  uint8_t message[MIRA_KERNEL_MESSAGE_CAPACITY];
} MiraKernelEvent;

typedef struct MiraKernelModuleState {
  uint8_t name[MIRA_KERNEL_MODULE_CAPACITY];
  uint32_t status;
  int32_t last_code;
  uint64_t updated_at_ms;
} MiraKernelModuleState;

int32_t mira_kernel_publish_event(
    uint32_t kind,
    int32_t code,
    const char* module,
    const char* message
);

int32_t mira_kernel_poll_event(MiraKernelEvent* out_event);

int32_t mira_kernel_set_module_state(
    const char* module,
    uint32_t status,
    int32_t last_code
);

int32_t mira_kernel_read_module_state(
    const char* module,
    MiraKernelModuleState* out_state
);

size_t mira_kernel_queue_depth(void);

#ifdef __cplusplus
}
#endif

#endif
