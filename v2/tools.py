"""Compatibility wrapper for the canonical Hermes tool registry."""

from agent.tools import TOOLS, dispatch_tool, get_tool_schema_xml

__all__ = ["TOOLS", "dispatch_tool", "get_tool_schema_xml"]
