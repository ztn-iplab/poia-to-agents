"""An AgentDojo model element for OpenAI's Responses API, which lets reasoning models call tools."""

import json

from agentdojo.agent_pipeline import BasePipelineElement
from agentdojo.functions_runtime import FunctionCall
from agentdojo.types import ChatAssistantMessage, get_text_content_as_str, text_content_block_from_string

OUTPUT = "responses_output"


def tool_spec(function):
    schema = function.parameters.model_json_schema()
    return {"type": "function", "name": function.name, "description": function.description, "parameters": schema}


def text_of(content):
    return get_text_content_as_str(content) if content else ""


def as_input(message):
    role = message["role"]
    if role == "system":
        return [{"role": "developer", "content": text_of(message["content"])}]
    if role == "user":
        return [{"role": "user", "content": text_of(message["content"])}]
    if role == "assistant":
        if message.get(OUTPUT):
            return list(message[OUTPUT])
        items = [{"role": "assistant", "content": text_of(message["content"])}] if text_of(message["content"]) else []
        for call in message["tool_calls"] or []:
            items.append(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.function,
                    "arguments": json.dumps(dict(call.args)),
                }
            )
        return items
    if role == "tool":
        output = message.get("error") or text_of(message["content"])
        return [{"type": "function_call_output", "call_id": message["tool_call_id"], "output": output}]
    raise ValueError(f"unknown role {role}")


def replayable(item):
    if item.type == "reasoning":
        summary = [part.model_dump() if hasattr(part, "model_dump") else dict(part) for part in item.summary or []]
        return {"type": "reasoning", "id": item.id, "summary": summary, "encrypted_content": item.encrypted_content}
    if item.type == "function_call":
        return {"type": "function_call", "call_id": item.call_id, "name": item.name, "arguments": item.arguments}
    if item.type == "message":
        return {
            "role": "assistant",
            "content": "".join(part.text for part in item.content if part.type == "output_text"),
        }
    return None


def as_message(response):
    kept = [replayable(item) for item in response.output]
    kept = [item for item in kept if item is not None]
    text = "".join(item["content"] for item in kept if item.get("role") == "assistant")
    calls = [
        FunctionCall(function=item["name"], args=json.loads(item["arguments"] or "{}"), id=item["call_id"])
        for item in kept
        if item.get("type") == "function_call"
    ]
    message = ChatAssistantMessage(
        role="assistant",
        content=[text_content_block_from_string(text)] if text or not calls else None,
        tool_calls=calls or None,
    )
    message[OUTPUT] = kept
    return message


class ResponsesLLM(BasePipelineElement):
    def __init__(self, client, model, reasoning_effort):
        self.client, self.model, self.reasoning_effort = client, model, reasoning_effort
        self.name = model

    def query(self, query, runtime, env=None, messages=(), extra_args=None):
        items = [item for message in messages for item in as_input(message)]
        tools = [tool_spec(function) for function in runtime.functions.values()]
        response = self.client.responses.create(
            model=self.model,
            input=items,
            tools=tools,
            reasoning={"effort": self.reasoning_effort},
            include=["reasoning.encrypted_content"],
            store=False,
        )
        return query, runtime, env, [*messages, as_message(response)], extra_args or {}
