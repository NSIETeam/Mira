"""WebSocket management contract."""

from mira.channels.contracts import ChannelSetupSpec
from mira.channels.plugin import ChannelPlugin
from mira.channels.websocket.validation import validate

SETUP_SPEC = ChannelSetupSpec(
    fields={},
    official_url="http://127.0.0.1:8765",
    validator=validate,
)

PLUGIN = ChannelPlugin(
    name="websocket",
    display_name="WebSocket",
    runtime=f"{__package__}.runtime:WebSocketChannel",
    setup=SETUP_SPEC,
    default_enabled=True,
    capabilities=frozenset({"always_enabled"}),
    tier="core",
    webui="webui/index.ts",
)
