"""Outbound POST integrations for form submissions and workflow events."""

from .dispatch import dispatch_outbound

__all__ = ["dispatch_outbound"]
