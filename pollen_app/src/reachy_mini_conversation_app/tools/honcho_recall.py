"""Honcho memory recall tool - query memories about the user."""

import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

logger = logging.getLogger(__name__)


class HonchoRecall(Tool):
    """Think deeply about what you know about this user from memory."""

    name = "recall"
    description = (
        "Think deeply about what you know about this user from previous conversations. "
        "Use this when you want to remember something about the person you're talking to, "
        "like their name, interests, or what you discussed before."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "A question about the user to search your memory for, e.g. 'What is their name?' or 'What do they like to talk about?'",
            }
        },
        "required": ["question"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Query Honcho memory about the user."""
        question = kwargs.get("question", "")

        # Access memory client from deps (will be added)
        memory = getattr(deps, "memory", None)
        if not memory:
            logger.warning("Memory not available in ToolDependencies")
            return {"memory": "I don't have access to my memory right now."}

        try:
            result = await memory.chat_about_user(question)
            if result:
                logger.info(f"Memory recall: {question!r} -> {result!r}")
                return {"memory": result}
            return {"memory": "I don't have any memories about that."}
        except Exception as e:
            logger.error(f"Memory recall failed: {e}")
            return {"error": str(e)}
