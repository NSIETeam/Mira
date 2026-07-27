#ifndef MIRA_BRIDGE_H
#define MIRA_BRIDGE_H

const char *mira_bridge_status_json(void);
int mira_bridge_attach_board(const char *transport, const char *port);

#endif
