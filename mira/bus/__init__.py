"""Message bus module for decoupled channel-agent communication."""

from mira.bus.events import InboundMessage, OutboundMessage
from mira.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
