"""Template coverage of the AgentDojo user tasks (RQ2)."""

import json
from collections import Counter
from pathlib import Path

from agentdojo.task_suite.load_suites import get_suite

BENCHMARK_VERSION = "v1.2.2"
SUITES = ("banking", "workspace", "slack", "travel")
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

WRITE_TOOLS = {
    "banking": {
        "send_money",
        "schedule_transaction",
        "update_scheduled_transaction",
        "update_password",
        "update_user_info",
    },
    "workspace": {
        "send_email",
        "delete_email",
        "create_calendar_event",
        "cancel_calendar_event",
        "reschedule_calendar_event",
        "add_calendar_event_participants",
        "append_to_file",
        "create_file",
        "delete_file",
        "share_file",
    },
    "slack": {
        "add_user_to_channel",
        "send_direct_message",
        "send_channel_message",
        "invite_user_to_slack",
        "remove_user_from_slack",
        "post_webpage",
    },
    "travel": {
        "reserve_hotel",
        "reserve_car_rental",
        "reserve_restaurant",
        "create_calendar_event",
        "cancel_calendar_event",
        "send_email",
    },
}

TASK_CLASSES = ("no state change", "template only", "template and fresh", "fresh only")


def load_catalog():
    return json.loads((TEMPLATES_DIR / "catalog.json").read_text())


def load_labels():
    return json.loads((TEMPLATES_DIR / "labels.json").read_text())


def decide(operation, always_fresh):
    """Return ("template", None) or ("fresh", reason) for one labeled operation."""
    if operation["tool"] in always_fresh:
        return "fresh", f"always fresh: {always_fresh[operation['tool']]}"
    if operation["action"] == "content":
        return "fresh", "action from content"
    sources = {target["source"] for target in operation["targets"]}
    if "content" in sources:
        return "fresh", "target from content"
    if "computed" in sources:
        return "fresh", "target computed by the agent"
    if operation.get("amount") == "content":
        return "fresh", "amount from content"
    return "template", None


def summarize_task(operations, always_fresh):
    templates, fresh, reasons = [], 0, []
    for operation in operations:
        decision, reason = decide(operation, always_fresh)
        if decision == "template":
            if operation["template"] not in templates:
                templates.append(operation["template"])
        else:
            fresh += 1
            reasons.append(reason)
    if not operations:
        task_class = "no state change"
    elif fresh == 0:
        task_class = "template only"
    elif templates:
        task_class = "template and fresh"
    else:
        task_class = "fresh only"
    return {
        "class": task_class,
        "operations": len(operations),
        "inside_template": len(operations) - fresh,
        "fresh": fresh,
        "templates": templates,
        "reasons": reasons,
        "approvals": len(templates) + fresh,
    }


def coverage():
    always_fresh = load_catalog()["always_fresh"]
    labels = load_labels()
    result = {}
    for suite_name in SUITES:
        suite = get_suite(BENCHMARK_VERSION, suite_name)
        tasks = [summarize_task(labels[suite_name].get(task_id, []), always_fresh) for task_id in suite.user_tasks]
        result[suite_name] = {
            "tasks": len(tasks),
            "classes": Counter(task["class"] for task in tasks),
            "operations": sum(task["operations"] for task in tasks),
            "inside_template": sum(task["inside_template"] for task in tasks),
            "fresh": sum(task["fresh"] for task in tasks),
            "approvals": sum(task["approvals"] for task in tasks),
            "reasons": Counter(reason for task in tasks for reason in task["reasons"]),
            "template_use": Counter(template for task in tasks for template in task["templates"]),
        }
    return result


def total(result, key):
    values = [result[suite][key] for suite in SUITES]
    if isinstance(values[0], Counter):
        return sum(values, Counter())
    return sum(values)


def main():
    result = coverage()
    columns = [*SUITES, "all"]

    def row(label, key, counter_key=None):
        cells = []
        for suite in SUITES:
            value = result[suite][key]
            cells.append(value[counter_key] if counter_key else value)
        cells.append(sum(cells))
        print(f"{label:<24}" + "".join(f"{cell:>11}" for cell in cells))

    print(f"{'':<24}" + "".join(f"{column:>11}" for column in columns))
    row("tasks", "tasks")
    for task_class in TASK_CLASSES:
        row(f"  {task_class}", "classes", task_class)
    row("operations", "operations")
    row("  inside a template", "inside_template")
    row("  fresh approval", "fresh")
    row("approvals", "approvals")

    print("\nreasons for a fresh approval")
    for reason, count in total(result, "reasons").most_common():
        print(f"  {count:>3}  {reason}")

    print("\ntasks that sign each template")
    for template, count in total(result, "template_use").most_common():
        print(f"  {count:>3}  {template}")


if __name__ == "__main__":
    main()
