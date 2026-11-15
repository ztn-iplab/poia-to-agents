"""A user task under the check: a simulated user, an agent key, and a runtime that asks before it changes state."""

import json
import secrets
from datetime import datetime, timedelta
from itertools import count

from agentdojo.functions_runtime import FunctionsRuntime

from poia_agents.check import Request, Service, Template, new_key, public_key, sign
from poia_agents.coverage import WRITE_TOOLS, decide, load_catalog, load_labels
from poia_agents.effects import effect_of

USER = "user"
NOW = datetime(2026, 1, 1)
EXPIRES = (NOW + timedelta(days=1)).isoformat()


def plain(arguments):
    given = {name: value for name, value in dict(arguments).items() if value is not None}
    return json.loads(json.dumps(given, default=str))


class Session:
    def __init__(self, suite_name, task_id, reference_calls, environment):
        catalog = load_catalog()
        self.always_fresh = catalog["always_fresh"]
        self.write_tools = WRITE_TOOLS[suite_name]
        self.environment = environment
        self.user_key = new_key()
        self.agent_key = new_key()
        self.service = Service(catalog, lambda tool, arguments: effect_of(tool, arguments, self.environment))
        self.service.register_user(USER, public_key(self.user_key))
        writes = [call for call in reference_calls if call.function in self.write_tools]
        self.intended = [(call.function, plain(call.args)) for call in writes]
        self.templates = self.sign_templates(load_labels()[suite_name].get(task_id, []))
        self.numbers = count(1)
        self.outcomes = []

    def sign_templates(self, labels):
        groups = {}
        for label, (tool, arguments) in zip(labels, self.intended, strict=True):
            if decide(label, self.always_fresh)[0] != "template":
                continue
            group = groups.setdefault(label["template"], {"targets": {}, "count": 0, "limit": None})
            for target in label["targets"]:
                named = group["targets"].setdefault(target["role"], [])
                named.extend(value for value in target.get("resolved", [target["value"]]) if value not in named)
            group["count"] += 1
            amount = effect_of(tool, arguments, self.environment).amount
            if amount is not None:
                group["limit"] = max(group["limit"] or 0.0, amount)
        templates = []
        for kind, group in groups.items():
            template = Template(
                template_id=secrets.token_hex(8),
                user=USER,
                agent_key=public_key(self.agent_key),
                kind=kind,
                targets=group["targets"],
                count=group["count"],
                expires=EXPIRES,
                limit=group["limit"],
            )
            decision = self.service.store_template(template, sign(self.user_key, template.message()))
            if not decision.allowed:
                raise RuntimeError(decision.reason)
            templates.append(template)
        return templates

    def view(self, tool, arguments):
        effect = effect_of(tool, arguments, self.environment)
        if tool in self.always_fresh or not (any(effect.targets.values()) or effect.amount is not None):
            return tool, arguments
        return tool, effect

    def intends(self, tool, arguments):
        asked = self.view(tool, arguments)
        for intended in self.intended:
            if self.view(*intended) == asked:
                self.intended.remove(intended)
                return True
        return False

    def executed(self, calls):
        outcomes = iter(self.outcomes)
        return [call for call in calls if call.function not in self.write_tools or next(outcomes)[1] != "refused"]

    def request(self, tool, arguments, environment):
        self.environment = environment
        arguments = plain(arguments)
        try:
            outcome = self.decide(tool, arguments)
        except (KeyError, TypeError, ValueError):
            outcome = "refused"
        self.outcomes.append((tool, outcome))
        return outcome

    def decide(self, tool, arguments):
        for template in self.templates:
            if tool in self.service.tools_of[template.kind]:
                request = Request(template.template_id, str(next(self.numbers)), tool, arguments)
                if self.service.authorize(request, sign(self.agent_key, request.message()), NOW).allowed:
                    self.intends(tool, arguments)
                    return "template"
        return "fresh" if self.intends(tool, arguments) else "refused"


class GuardedRuntime(FunctionsRuntime):
    def __init__(self, functions, session):
        super().__init__(functions)
        self.session = session

    def run_function(self, env, function, kwargs, raise_on_error=False):
        if function in self.session.write_tools and self.session.request(function, kwargs, env) == "refused":
            return "", f"PermissionError: `{function}` is outside the user's approval and was not executed."
        return super().run_function(env, function, kwargs, raise_on_error)
