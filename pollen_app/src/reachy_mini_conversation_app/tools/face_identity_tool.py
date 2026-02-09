"""Tool for face identity - who is Reachy talking to."""

from typing import Any

from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


def get_tool_spec() -> dict:
    """OpenAI function spec for face identity tool."""
    return {
        "name": "identify_person",
        "description": (
            "Get or set the identity of the person you're talking to. "
            "Use this to learn their name or remember who they are. "
            "If they tell you their name, use action='set_name' to remember it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "set_name", "list_all"],
                    "description": "get=who is current person, set_name=save their name, list_all=list everyone I know",
                },
                "name": {
                    "type": "string",
                    "description": "The person's name (only for set_name action)",
                },
            },
            "required": ["action"],
        },
    }


async def execute(args: dict, deps: ToolDependencies) -> dict[str, Any]:
    """Execute face identity action."""
    action = args.get("action", "get")
    face_identity = getattr(deps, "face_identity", None)

    if face_identity is None:
        return {"error": "Face identity not available", "status": "disabled"}

    if action == "get":
        user_id, name = face_identity.get_current_user()
        if user_id:
            return {
                "status": "identified",
                "user_id": user_id,
                "name": name or "Unknown",
                "message": f"You are talking to {name or 'someone new'}",
            }
        return {
            "status": "no_face",
            "message": "I can't see anyone right now",
        }

    elif action == "set_name":
        name = args.get("name", "").strip()
        if not name:
            return {"error": "No name provided"}
        success = face_identity.rename_current_user(name)
        if success:
            return {
                "status": "saved",
                "name": name,
                "message": f"I'll remember you as {name}!",
            }
        return {"error": "No one to rename - I need to see a face first"}

    elif action == "list_all":
        users = face_identity.registry.list_users()
        if users:
            names = [u["name"] for u in users]
            return {
                "status": "success",
                "count": len(users),
                "people": names,
                "message": f"I know {len(users)} people: {', '.join(names)}",
            }
        return {
            "status": "empty",
            "message": "I haven't met anyone yet!",
        }

    return {"error": f"Unknown action: {action}"}
