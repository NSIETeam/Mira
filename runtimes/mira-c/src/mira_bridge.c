#include "mira_bridge.h"

static const char *MIRA_BRIDGE_READY =
    "{\"runtime\":\"mira-c\",\"status\":\"ready\",\"abi\":\"c\",\"mode\":\"serial\",\"kernel_surface\":\"mira\",\"version\":\"0.1.0\",\"queue_depth\":0,\"module_count\":2,\"updated_at_ms\":0,\"board_io\":true,\"capabilities\":[\"fault_stream\",\"module_state\",\"diagnostics\",\"board_io\",\"firmware_bridge\"],\"module_states\":{\"bridge\":{\"status\":\"ready\",\"last_code\":0},\"board\":{\"status\":\"ready\",\"last_code\":0}},\"last_command\":{\"target\":\"board\",\"action\":\"status\",\"status\":\"ready\",\"code\":0,\"updated_at_ms\":0}}";

const char *mira_bridge_status_json(void) {
    return MIRA_BRIDGE_READY;
}

int mira_bridge_attach_board(const char *transport, const char *port) {
    (void)transport;
    (void)port;
    return 0;
}
