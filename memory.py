"""Honcho memory integration for persistent user context.

Wraps the Honcho API v2 for conversation memory with per-user sessions.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Honcho client
try:
    from honcho import Honcho
    HONCHO_AVAILABLE = True
except ImportError:
    HONCHO_AVAILABLE = False
    logger.warning("Honcho not available - memory disabled")


class ConversationMemory:
    """Wrapper for Honcho memory with per-user sessions."""

    def __init__(
        self,
        app_name: str = "reachy-mini",
    ):
        """Initialize Honcho client."""
        self.app_name = app_name
        self._client = None
        self._sessions = {}  # user_id -> session object

        api_key = os.getenv("HONCHO_API_KEY")
        if not api_key:
            logger.warning("HONCHO_API_KEY not set - memory disabled")
            return

        if not HONCHO_AVAILABLE:
            return

        try:
            workspace_id = os.getenv("HONCHO_WORKSPACE_ID", "default")
            self._client = Honcho(api_key=api_key, workspace_id=workspace_id)
            logger.info(f"Honcho connected: workspace={workspace_id}, app={self.app_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Honcho: {e}")
            self._client = None

    def is_available(self) -> bool:
        """Check if Honcho is available and configured."""
        return self._client is not None

    def _get_or_create_session(self, user_id: str):
        """Get or create a session for a user."""
        if not self.is_available():
            return None

        if user_id in self._sessions:
            return self._sessions[user_id]

        try:
            session_id = f"{self.app_name}-{user_id}"
            session = self._client.session(id=session_id)
            # Add peers for user and assistant
            try:
                session.add_peers(["user", "assistant"])
            except Exception:
                pass  # Peers may already exist
            self._sessions[user_id] = session
            logger.info(f"Got Honcho session for {user_id}: {session_id}")
            return session
        except Exception as e:
            logger.error(f"Failed to create session for {user_id}: {e}")
            return None

    async def get_context(self, user_id: str) -> str:
        """Get memory context for a user."""
        if not self.is_available():
            return ""

        try:
            session = self._get_or_create_session(user_id)
            if not session:
                return ""

            results = session.search(query="What do I know about this user?")
            if results:
                context_parts = []
                for r in results:
                    if hasattr(r, 'content'):
                        context_parts.append(r.content)
                return "\n".join(context_parts) if context_parts else ""
            return ""
        except Exception as e:
            logger.debug(f"Failed to get context for {user_id}: {e}")
            return ""

    async def save(self, user_id: str, user_msg: str, assistant_msg: str) -> bool:
        """Save a conversation exchange to memory."""
        if not self.is_available():
            return False

        try:
            session = self._get_or_create_session(user_id)
            if not session:
                return False

            # Add messages with peer_id
            session.add_messages({"peer_id": "user", "content": user_msg})
            session.add_messages({"peer_id": "assistant", "content": assistant_msg})
            logger.debug(f"Saved exchange to Honcho for {user_id}")
            return True
        except Exception as e:
            logger.debug(f"Failed to save to memory for {user_id}: {e}")
            return False

    async def chat_about_user(self, user_id: str, question: str) -> str:
        """Query Honcho about a specific question regarding the user."""
        if not self.is_available():
            return "I don't have access to my memory right now."

        try:
            session = self._get_or_create_session(user_id)
            if not session:
                return "I don't have access to my memory right now."

            results = session.search(query=question)
            if results:
                for r in results:
                    if hasattr(r, 'content'):
                        return r.content
            return "I don't have any memories about that."
        except Exception as e:
            logger.debug(f"Failed to chat about user {user_id}: {e}")
            return "I couldn't access my memory right now."

    async def create_conclusion(self, user_id: str, fact: str) -> bool:
        """Save an important fact about the user to long-term memory."""
        if not self.is_available():
            return False

        try:
            session = self._get_or_create_session(user_id)
            if not session:
                return False

            session.add_messages({"peer_id": "user", "content": f"Remember: {fact}"})
            session.add_messages({"peer_id": "assistant", "content": f"I'll remember: {fact}"})
            logger.info(f"Saved conclusion for {user_id}: {fact}")
            return True
        except Exception as e:
            logger.debug(f"Failed to create conclusion for {user_id}: {e}")
            return False
