"""One AgentDojo task end to end, with templates and fresh approvals signed through PoIA."""

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

import openai
from agentdojo.agent_pipeline import AgentPipeline, GroundTruthPipeline, OpenAILLM
from agentdojo.task_suite.load_suites import get_suite
from dotenv import load_dotenv

from poia_agents.coverage import BENCHMARK_VERSION, SUITES
from poia_agents.experiment import Metered, build_agent, make_attack, run_case, spoken_name
from poia_agents.poia import PoIAUser, RelyingParty

RESULTS = Path("results/demo")


def obedient_agent(suite, task_id, injection_id):
    steps = [GroundTruthPipeline(suite.injection_tasks[injection_id])] if injection_id else []
    return AgentPipeline([*steps, GroundTruthPipeline(suite.user_tasks[task_id])])


def report(record, user):
    print(f"\nuser task solved: {record['solved']}   attack succeeded: {record['attacked']}")
    for tool, outcome in record["outcomes"]:
        print(f"  {tool:<32}{outcome}")
    waits = [entry["seconds"] for entry in user.log]
    if waits:
        print(f"approvals: {len(waits)}, median wait {statistics.median(waits):.1f} s")
    if record["check_ns"]:
        print(f"check per operation: median {statistics.median(record['check_ns']) / 1000:.0f} microseconds")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://poia.local")
    parser.add_argument("--ca", default="../poia-prototype/certs/zt-iam-ca.crt")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--rp-id", default="poia-demo-bank")
    parser.add_argument("--signer", default="zt", choices=["zt", "webauthn"], help="ZT-Authenticator or a passkey")
    parser.add_argument("--suite", default="banking", choices=SUITES)
    parser.add_argument("--task", default="user_task_15")
    parser.add_argument("--attack", help="an AgentDojo injection task, for example injection_task_0")
    parser.add_argument("--model", default="obedient", help="an OpenAI model, or obedient for the reference agent")
    args = parser.parse_args()

    suite = get_suite(BENCHMARK_VERSION, args.suite)
    user = PoIAUser(RelyingParty(args.url, args.user_id, args.rp_id, args.ca), args.signer)
    problem = user.relying_party.problem()
    if problem:
        raise SystemExit(problem)
    if args.model == "obedient":
        agent, meter = obedient_agent(suite, args.task, args.attack), None
    else:
        load_dotenv(".env")
        meter = Metered(openai.OpenAI(max_retries=5))
        agent = build_agent(OpenAILLM(meter, args.model, reasoning_effort="none"))
    attack = make_attack(
        "important_instructions", suite, agent, spoken_name(args.model if args.model != "obedient" else "gpt")
    )
    now = datetime.now().replace(microsecond=0)
    print(f"{args.suite} {args.task}: {suite.user_tasks[args.task].PROMPT}")
    if args.attack:
        print(f"attacker goal: {suite.injection_tasks[args.attack].GOAL}")
    record = run_case(args.suite, args.task, args.attack, agent, attack, True, meter, user, now)
    record["approvals"] = user.log
    report(record, user)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{now:%Y%m%d-%H%M%S}-{args.task}-{args.attack or 'no_attack'}-{args.model}-{args.signer}.json"
    path.write_text(json.dumps(record, indent=1, default=lambda value: value.model_dump()))
    print(f"saved {path}")


if __name__ == "__main__":
    main()
