"""Shared LangChain binding for every skill's `adapter.py`.

Importing this module is free of LangChain; `skill_tool` loads it on first use, so the
core stays installable with Pydantic alone.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping

from pydantic import ValidationError

from .base import BaseSkill, ModelSettings, SkillModel, validation_details

if TYPE_CHECKING:
    from langchain_core.tools import StructuredTool


def _alias(input_type: type[SkillModel], field: str) -> str:
    return input_type.model_fields[field].alias or field


def agent_schema(input_type: type[SkillModel], hidden: set[str]) -> dict[str, Any]:
    """The input JSON schema an agent sees: host-bound fields removed, unused defs pruned."""
    schema = input_type.model_json_schema(by_alias=True)
    hidden_aliases = {_alias(input_type, field) for field in hidden}
    for alias in hidden_aliases:
        schema.get("properties", {}).pop(alias, None)
    required = [name for name in schema.get("required", []) if name not in hidden_aliases]
    if required:
        schema["required"] = required
    else:
        schema.pop("required", None)
    # Keep only definitions still reachable once the hidden fields are gone.
    definitions = schema.pop("$defs", {})
    live: dict[str, Any] = {}
    pending = [schema]
    while pending:
        text = json.dumps(pending.pop())
        for name, body in definitions.items():
            if name not in live and f'"#/$defs/{name}"' in text:
                live[name] = body
                pending.append(body)
    if live:
        schema["$defs"] = {name: definitions[name] for name in definitions if name in live}
    return schema


def skill_tool(
    skill_type: type[BaseSkill[Any, Any]],
    run: Callable[[Any], Awaitable[str]],
    *,
    model: ModelSettings | Mapping[str, Any] | None = None,
    host_inputs: Mapping[str, Any] | None = None,
) -> "StructuredTool":
    """Bind an authorized host runner as a tool whose schema carries only agent-owned fields.

    Provider, model ID and base URL are authorization decisions, so a skill that takes
    `model` never exposes it: the host passes its resolved `ModelSettings` here and the
    agent can neither read nor override them. `host_inputs` binds further fields the same
    way — references the host resolved through its own ownership checks, for instance.

    Invalid arguments come back to the agent as a sanitized tool message listing field
    paths and error types; the raw `ValidationError`, which holds the offending prompt or
    URL, never leaves this function.
    """
    from langchain_core.tools import StructuredTool, ToolException

    input_type = skill_type.input_schema
    bound: dict[str, Any] = dict(host_inputs or {})
    unknown = sorted(set(bound) - set(input_type.model_fields))
    if unknown:
        raise ValueError(f"{skill_type.name} has no input field named {', '.join(unknown)}")
    if "model" in input_type.model_fields:
        if model is None and "model" not in bound:
            raise ValueError(f"{skill_type.name} needs host-resolved model settings")
        if model is not None:
            bound["model"] = model
    elif model is not None:
        raise ValueError(f"{skill_type.name} does not take model settings")
    reserved = {name for field in bound for name in (field, _alias(input_type, field))}

    async def invoke(**kwargs: Any) -> str:
        supplied = sorted(reserved & set(kwargs))
        if supplied:
            raise ToolException(f"Invalid arguments: {', '.join(supplied)} is set by the host and cannot be supplied")
        try:
            inputs = input_type.model_validate({**kwargs, **bound})
        except ValidationError as exc:
            # `from None`: the chained error would carry the raw input into host logs.
            raise ToolException("Invalid arguments: " + "; ".join(validation_details(exc))) from None
        return await run(inputs)

    return StructuredTool.from_function(
        coroutine=invoke, name=skill_type.name, description=skill_type.description,
        # A JSON schema avoids LangChain dropping camelCase aliases before invoke.
        # The Pydantic model validates inside invoke, including unknown fields.
        args_schema=agent_schema(input_type, set(bound)),
        handle_tool_error=True,
    )
