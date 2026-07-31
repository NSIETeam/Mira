"""WeCom management contract."""

from mira.channels._manifest import field, required_fields
from mira.channels.contracts import ChannelSetupSpec
from mira.channels.plugin import ChannelPlugin

SETUP_SPEC = ChannelSetupSpec(
    fields={
        "botId": field(),
        "secret": field("secret"),
        "allowFrom": field("list"),
    },
    required=required_fields("botId", "secret"),
    official_url="https://developer.work.weixin.qq.com/",
)

PLUGIN = ChannelPlugin(
    name="wecom",
    display_name="WeCom",
    runtime=f"{__package__}.runtime:WecomChannel",
    setup=SETUP_SPEC,
    dependencies=("wecom-aibot-sdk-python>=0.1.5",),
    tier="archive",
    webui="webui/index.ts",
)
