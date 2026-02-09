"""Honcho memory save tool - save important facts about the user."""

import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

logger = logging.getLogger(__name__)


class HonchoRemember(Tool):
    """Save an important fact about the user to long-term memory."""

    name = "create_conclusion"
    description = (
        "Permanently save an important fact about the user to your long-term memory. "
        "Use this when you learn something worth remembering, like their name, "
        "preferences, or important life details."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "A concise, standalone fact about the user to remember, e.g. 'Their name is Alex' or 'They love playing chess'",
            }
        },
        "required": ["fact"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Save a fact to Honcho memory."""
        fact = kwargs.get("fact", "")

        if not fact or not fact.strip():
            return {"error": "No fact provided to remember"}

        # Access memory client from deps (will be added)
        memory = getattr(deps, "memory", None)
        if not memory:
            logger.warning("Memory not available in ToolDependencies")
            return {"saved": False, "error": "Memory not available"}

        try:
            success = await memory.create_conclusion(fact)
            if success:
                logger.info(f"Saved to memory: {fact!r}")
                return {"saved": True, "fact": fact}
            return {"saved": False, "error": "Failed to save to memory"}
        except Exception as e:
            logger.error(f"Memory save failed: {e}")
            return {"saved": False, "error": str(e)}
