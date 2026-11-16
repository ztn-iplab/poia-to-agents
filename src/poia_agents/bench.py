"""Time taken by the check: per operation, and per template approval verified through PoIA."""

import argparse
import json
import platform
import statistics
from datetime import datetime
from pathlib import Path
from time import perf_counter_ns

from poia_agents.check import Effect, Request, Service, Template, new_key, public_key, sign, verify
from poia_agents.coverage import load_catalog
from poia_agents.devices import Passkey, Phone, signed
from poia_agents.poia import TEMPLATE_ACTION, approved

RESULTS = Path("results/bench")
PAYEES = [f"GB{n:020d}" for n in range(10)]
NOW = datetime(2026, 11, 15, 12, 0)


def interpret(tool, arguments):
    return Effect({"payee": [arguments["recipient"]]}, arguments["amount"])


def timed(function, items):
    times = []
    for item in items:
        started = perf_counter_ns()
        function(item)
        times.append(perf_counter_ns() - started)
    return times


def summary(times):
    ordered = sorted(times)
    return {
        "median_us": round(statistics.median(ordered) / 1000, 1),
        "p99_us": round(ordered[int(0.99 * (len(ordered) - 1))] / 1000, 1),
        "runs": len(ordered),
    }


def operations(count):
    user, agent = new_key(), new_key()
    service = Service(load_catalog(), interpret)
    service.register_user("user", public_key(user))
    template = Template(
        "bench", "user", public_key(agent), "pay", {"payee": PAYEES}, count, "2026-11-16T12:00:00", 100.0
    )
    assert service.store_template(template, sign(user, template.message())).allowed
    requests = []
    for number in range(count):
        arguments = {"recipient": PAYEES[number % 10], "amount": 10.0, "subject": "bench", "date": "2026-11-15"}
        request = Request("bench", str(number), "send_money", arguments)
        requests.append((request, sign(agent, request.message())))
    return service, template, requests


def measure(count):
    service, template, requests = operations(count)
    check = timed(lambda item: service.authorize(item[0], item[1], NOW), requests)
    assert service.remaining["bench"] == 0
    signature = timed(lambda item: verify(template.agent_key, item[0].message(), item[1]), requests)
    scope, rp = template.message(), "poia-demo-bank"
    phone = [signed(Phone(), TEMPLATE_ACTION, scope, 1, rp) for _ in range(count // 10)]
    passkey = [signed(Passkey(), TEMPLATE_ACTION, scope, 1, rp) for _ in range(count // 10)]
    zt = timed(lambda record: approved(record, TEMPLATE_ACTION, scope, 1, rp), phone)
    webauthn = timed(lambda record: approved(record, TEMPLATE_ACTION, scope, 1, rp), passkey)
    assert all(approved(record, TEMPLATE_ACTION, scope, 1, rp) for record in phone + passkey)
    return {
        "check per operation": summary(check),
        "  agent signature alone": summary(signature),
        "template approval, ZT-Authenticator": summary(zt),
        "template approval, passkey": summary(webauthn),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operations", type=int, default=10_000)
    args = parser.parse_args()
    result = measure(args.operations)
    print(f"{'':<40}{'median (us)':>14}{'p99 (us)':>12}{'runs':>8}")
    for name, values in result.items():
        print(f"{name:<40}{values['median_us']:>14}{values['p99_us']:>12}{values['runs']:>8}")
    machine = {"machine": platform.machine(), "system": platform.platform(), "python": platform.python_version()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-{platform.node() or 'host'}.json"
    path.write_text(json.dumps({"machine": machine, "results": result}, indent=1))
    print(f"saved {path}")


if __name__ == "__main__":
    main()
