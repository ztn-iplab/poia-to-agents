"""The check a service runs before it executes an operation an agent requests."""

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(message):
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode()


def new_key():
    return Ed25519PrivateKey.generate()


def public_key(private_key):
    return private_key.public_key().public_bytes_raw().hex()


def sign(private_key, message):
    return private_key.sign(canonical(message)).hex()


def verify(key, message, signature):
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(bytes.fromhex(signature), canonical(message))
    except (InvalidSignature, ValueError):
        return False
    return True


@dataclass(frozen=True)
class Template:
    template_id: str
    user: str
    agent_key: str
    kind: str
    targets: dict
    count: int
    expires: str
    limit: float | None = None

    def message(self):
        return {"type": "template", **asdict(self)}


@dataclass(frozen=True)
class Request:
    template_id: str
    number: str
    tool: str
    arguments: dict

    def message(self):
        return {"type": "operation", **asdict(self)}


@dataclass(frozen=True)
class Effect:
    targets: dict = field(default_factory=dict)
    amount: float | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    condition: str | None = None
    reason: str = ""


ALLOWED = Decision(True)


def refuse(condition, reason):
    return Decision(False, condition, reason)


class Service:
    def __init__(self, catalog, interpret):
        self.tools_of = {template["id"]: set(template["tools"]) for template in catalog["templates"]}
        self.always_fresh = set(catalog["always_fresh"])
        self.interpret = interpret
        self.user_keys = {}
        self.templates = {}
        self.remaining = {}
        self.used_numbers = set()
        self.lock = threading.Lock()

    def register_user(self, user, key):
        self.user_keys[user] = key

    def store_template(self, template, signature):
        key = self.user_keys.get(template.user)
        if key is None or not verify(key, template.message(), signature):
            return refuse("C1", "the user's signature on the template is not valid")
        with self.lock:
            if template.template_id in self.templates:
                return refuse("C1", "the template has been stored before")
            self.templates[template.template_id] = template
            self.remaining[template.template_id] = template.count
        return ALLOWED

    def authorize(self, request, signature, now):
        template = self.templates.get(request.template_id)
        if template is None:
            return refuse("C1", "no stored template has this identifier")
        if not verify(template.agent_key, request.message(), signature):
            return refuse("C2", "the request is not signed by the agent key named in the template")
        if request.tool in self.always_fresh:
            return refuse("C6", "the operation always needs a fresh approval")
        if request.tool not in self.tools_of[template.kind]:
            return refuse("C4", "the template does not cover this tool")
        effect = self.interpret(request.tool, request.arguments)
        for role, values in effect.targets.items():
            named = template.targets.get(role, [])
            if any(value not in named for value in values):
                return refuse("C4", f"a {role} is not named in the template")
        if effect.amount is not None and (template.limit is None or effect.amount > template.limit):
            return refuse("C4", "the amount is over the limit")
        if now >= datetime.fromisoformat(template.expires):
            return refuse("C4", "the template has expired")
        with self.lock:
            if (request.template_id, request.number) in self.used_numbers:
                return refuse("C3", "the operation number has been used before")
            if self.remaining[request.template_id] == 0:
                return refuse("C5", "the allowed number of operations is used up")
            self.used_numbers.add((request.template_id, request.number))
            self.remaining[request.template_id] -= 1
        return ALLOWED

