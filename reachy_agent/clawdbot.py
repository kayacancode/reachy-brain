"""Clawdbot client - your AI brain."""

import logging
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class ClawdbotClient:
    """Client for Clawdbot chat completions API."""

    def __init__(
        self,
        endpoint: str,
        token: str,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.endpoint = endpoint
        self.token = token
        self.model = model
        self._client = httpx.AsyncClient(timeout=30.0)
        self._conversation_history: list[dict] = []

    async def chat(
        self,
        user_message: str,
        system_prompt: str,
        user_context: str | None = None,
    ) -> str:
        """Send a message to Clawdbot and get a response.

        Args:
            user_message: The user's transcribed speech
            system_prompt: System instructions for the AI
            user_context: Optional context about the user (from Honcho)

        Returns:
            The AI's response text
        """
        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        # Add user context if available
        if user_context:
            messages.append({
                "role": "system",
                "content": f"[User Context from Memory]\n{user_context}"
            })

        # Add conversation history
        messages.extend(self._conversation_history)

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 150,  # Keep responses short for voice
            "temperature": 0.7,
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.post(
                self.endpoint,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            if "choices" in data and data["choices"]:
                assistant_message = data["choices"][0]["message"]["content"].strip()

                # Update conversation history
                self._conversation_history.append({"role": "user", "content": user_message})
                self._conversation_history.append({"role": "assistant", "content": assistant_message})

                # Keep history manageable (last 10 exchanges)
                if len(self._conversation_history) > 20:
                    self._conversation_history = self._conversation_history[-20:]

                return assistant_message

            logger.error(f"Unexpected response format: {data}")
            return "I'm having trouble thinking right now."

        except httpx.HTTPStatusError as e:
            logger.error(f"Clawdbot API error: {e.response.status_code} - {e.response.text}")
            return "I'm having trouble connecting to my brain."
        except Exception as e:
            logger.error(f"Clawdbot error: {e}")
            return "Something went wrong. Let me try again."

    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str,
        user_context: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a response from Clawdbot (for future streaming TTS).

        Yields chunks of the response as they arrive.
        """
        # Build messages same as chat()
        messages = [{"role": "system", "content": system_prompt}]

        if user_context:
            messages.append({
                "role": "system",
                "content": f"[User Context from Memory]\n{user_context}"
            })

        messages.extend(self._conversation_history)
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.7,
            "stream": True,
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        full_response = ""

        try:
            async with self._client.stream(
                "POST",
                self.endpoint,
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        import json
                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and chunk["choices"]:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_response += content
                                    yield content
                        except json.JSONDecodeError:
                            continue

            # Update history after complete response
            if full_response:
                self._conversation_history.append({"role": "user", "content": user_message})
                self._conversation_history.append({"role": "assistant", "content": full_response})

                if len(self._conversation_history) > 20:
                    self._conversation_history = self._conversation_history[-20:]

        except Exception as e:
            logger.error(f"Clawdbot stream error: {e}")
            yield "Something went wrong."

    def clear_history(self) -> None:
        """Clear conversation history (e.g., when switching users)."""
        self._conversation_history = []
        logger.debug("Cleared Clawdbot conversation history")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
