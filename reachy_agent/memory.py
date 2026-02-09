"""Conversation memory using Honcho."""

import asyncio
import json
import logging
from dataclasses import dataclass

from honcho import Honcho
from honcho.api_types import PeerConfig

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """Queued message pending persistence to Honcho."""

    session: object
    peer: object
    content: str
    attempts: int = 0


class ConversationMemory:
    """Manages conversation history with Honcho."""

    def __init__(self, api_key: str, workspace_name: str = "reachy-mini"):
        self._api_key = api_key
        self._workspace_name = workspace_name
        self._client = None
        self._user_sessions: dict[str, object] = {}
        self._user_peers: dict[str, object] = {}
        self._active_user_id: str | None = None
        self._robot_peer = None
        self._robot_peer_id = "reachy"
        self._message_queue: asyncio.Queue[QueuedMessage] | None = None
        self._worker_task: asyncio.Task | None = None
        self._worker_shutdown = asyncio.Event()
        self._max_save_retries = 3

    async def initialize(self) -> None:
        """Initialize workspace and robot peer."""
        if not self._api_key:
            logger.info("Honcho API key missing, memory disabled")
            return

        self._client = Honcho(
            api_key=self._api_key,
            workspace_id=self._workspace_name,
        )

        self._robot_peer = await self._client.aio.peer(
            self._robot_peer_id,
            metadata={"type": "robot", "model": "reachy-mini"},
            configuration=PeerConfig(observe_me=False),
        )

        self._message_queue = asyncio.Queue()
        self._worker_shutdown = asyncio.Event()
        self._worker_task = asyncio.create_task(
            self._message_worker(), name="honcho_save_worker"
        )

        logger.info(f"Memory initialized: workspace={self._workspace_name}")

    async def _message_worker(self) -> None:
        """Persist queued messages to Honcho in the background."""
        if not self._message_queue:
            return

        while True:
            if self._worker_shutdown.is_set() and self._message_queue.empty():
                break

            try:
                item = await asyncio.wait_for(self._message_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            try:
                await item.session.aio.add_messages(item.peer.message(item.content))
            except Exception as e:
                logger.warning(f"Honcho save failed: {e}")
                if item.attempts < self._max_save_retries:
                    item.attempts += 1
                    await asyncio.sleep(min(2**item.attempts, 5))
                    if self._message_queue:
                        await self._message_queue.put(item)
            finally:
                self._message_queue.task_done()

    async def _enqueue_message(
        self, session: object, peer: object, content: str
    ) -> None:
        """Queue a message for background persistence."""
        if not self._message_queue:
            return

        if not content:
            return

        await self._message_queue.put(
            QueuedMessage(session=session, peer=peer, content=content)
        )

    async def _get_user_peer(self, user_id: str) -> object:
        """Lazy-create Honcho peer for user."""
        if user_id in self._user_peers:
            return self._user_peers[user_id]
        peer = await self._client.aio.peer(user_id, metadata={"type": "human"})
        self._user_peers[user_id] = peer
        logger.debug(f"Created Honcho peer: {user_id}")
        return peer

    async def _get_user_session(self, user_id: str) -> object:
        """Lazy-create Honcho session for user."""
        if user_id in self._user_sessions:
            return self._user_sessions[user_id]
        session_id = f"reachy-chat-{user_id}"
        session = await self._client.aio.session(session_id)
        self._user_sessions[user_id] = session
        logger.debug(f"Created Honcho session: {session_id}")
        return session

    def set_active_user(self, user_id: str) -> bool:
        """Set currently speaking user. Returns True if user changed."""
        changed = self._active_user_id != user_id
        if changed:
            logger.info(f"Active user: {user_id}")
        self._active_user_id = user_id
        return changed

    async def add_user_message(self, content: str) -> None:
        """Record a message from the user."""
        if not self._client:
            return

        user_id = self._active_user_id or "user"
        session = await self._get_user_session(user_id)
        peer = await self._get_user_peer(user_id)
        await self._enqueue_message(session, peer, content)
        logger.debug(f"User ({user_id}): {content[:50]}...")

    async def add_robot_message(self, content: str) -> None:
        """Record a message from Reachy."""
        if not self._client or not self._robot_peer:
            return

        user_id = self._active_user_id or "user"
        session = await self._get_user_session(user_id)
        await self._enqueue_message(session, self._robot_peer, content)
        logger.debug(f"Reachy: {content[:50]}...")

    async def get_rich_context(self) -> str:
        """Fetch context from multiple sources in parallel."""
        if not self._client or not self._robot_peer:
            return ""

        user_id = self._active_user_id or "user"
        try:
            session = await self._get_user_session(user_id)
            session_context = await session.aio.context(
                tokens=8192, peer_target=user_id
            )
            return json.dumps(
                {
                    "user_representation": session_context.peer_representation,
                    "peer_card": session_context.peer_card,
                    "recent_messages": session_context.messages,
                },
                default=str,
            )
        except Exception as e:
            logger.error(f"Failed to fetch session context: {e}")
            return ""

    async def chat_about_user(self, query: str) -> str | None:
        """Ask dialectic AI about the user."""
        logger.info(f"chat_about_user: query={query!r}")
        if not self._robot_peer or not self._client:
            logger.warning("chat_about_user: no peers")
            return None
        user_id = self._active_user_id or "user"
        query = f"Question from user `reachy` regarding user {user_id}: {query}"
        try:
            user_peer = await self._get_user_peer(user_id)
            session = await self._get_user_session(user_id)
            result = await user_peer.aio.chat(
                query, session=session, reasoning_level="medium"
            )
            logger.info(f"chat_about_user: result={result!r}")
            return result
        except Exception as e:
            logger.warning(f"chat_about_user failed: {e}")
            return None

    async def create_conclusion(self, fact: str) -> bool:
        """Create a conclusion (fact) about the current user from the robot's perspective.

        Returns True if the conclusion was created successfully.
        """
        if not self._client or not self._robot_peer:
            return False

        user_id = self._active_user_id or "user"
        try:
            peer = await self._client.aio.peer(user_id)
            await peer.conclusions_of(user_id).aio.create([{"content": fact}])
            logger.info(f"Created conclusion for {user_id}: {fact}")
            return True
        except Exception as e:
            logger.warning(f"Failed to create conclusion for {user_id}: {e}")
            return False

    async def get_user_briefing(self, user_id: str) -> str | None:
        """Get a briefing about a user when they're recognized.

        Returns key information to help contextualize the conversation.
        """
        if not self._client:
            return None
        try:
            user_peer = await self._get_user_peer(user_id)
            session = await self._get_user_session(user_id)
            query = (
                f"A user just started speaking to me (Reachy, a robot). "
                f"What are the most important things I should know about {user_id}? "
                f"Include their name if known, key interests, recent topics we discussed, "
                f"and anything that would help me have a personalized conversation. "
                f"Be concise - just the essentials."
            )
            result = await user_peer.aio.chat(
                query, session=session, reasoning_level="low"
            )
            logger.info(f"User briefing for {user_id}: {result!r}")
            return result
        except Exception as e:
            logger.warning(f"get_user_briefing failed for {user_id}: {e}")
            return None

    async def close(self) -> None:
        """Close the client."""
        if self._worker_shutdown:
            self._worker_shutdown.set()

        if self._worker_task:
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        self._worker_task = None
        self._message_queue = None
        self._client = None
        self._user_sessions = {}
        self._user_peers = {}
        self._active_user_id = None
        self._robot_peer = None
