#include "mira_bridge.h"

static const char *MIRA_BRIDGE_READY =
    "{\"runtime\":\"mira-c\",\"status\":\"ready\",\"mode\":\"serial\",\"board_io\":true}";

const char *mira_bridge_status_json(void) {
    return MIRA_BRIDGE_READY;
}

int mira_bridge_attach_board(const char *transport, const char *port) {
    (void)transport;
    (void)port;
    return 0;
}
