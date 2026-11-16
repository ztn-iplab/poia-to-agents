"""What an AgentDojo tool call affects: its targets and, where money moves, its amount."""

from poia_agents.check import Effect


def site(url):
    url = url.strip().lower()
    for scheme in ("https://", "http://"):
        url = url.removeprefix(scheme)
    return url.rstrip("/")


def filename(environment, file_id):
    file = environment.cloud_drive.files.get(file_id)
    return file.filename if file else file_id


def effect_of(tool, arguments, environment):
    a = arguments
    match tool:
        case "send_money" | "schedule_transaction":
            return Effect({"payee": [a["recipient"]]}, float(a["amount"]))
        case "update_scheduled_transaction":
            targets = {"standing_order": [str(a["id"])]}
            if a.get("recipient") is not None:
                targets["payee"] = [a["recipient"]]
            amount = a.get("amount")
            return Effect(targets, None if amount is None else float(amount))
        case "send_email":
            return Effect({"recipient": [*a["recipients"], *(a.get("cc") or []), *(a.get("bcc") or [])]})
        case "create_calendar_event":
            return Effect({"invitee": list(a.get("participants") or [])})
        case "reschedule_calendar_event" | "cancel_calendar_event":
            return Effect({"event": [a["event_id"]]})
        case "add_calendar_event_participants":
            return Effect({"event": [a["event_id"]], "invitee": list(a["participants"])})
        case "append_to_file" | "delete_file":
            return Effect({"file": [filename(environment, a["file_id"])]})
        case "share_file":
            return Effect(
                {"file": [filename(environment, a["file_id"])], "person": [a["email"]], "access": [a["permission"]]}
            )
        case "send_direct_message":
            return Effect({"member": [a["recipient"]]})
        case "send_channel_message":
            return Effect({"channel": [a["channel"]]})
        case "add_user_to_channel":
            return Effect({"member": [a["user"]], "channel": [a["channel"]]})
        case "post_webpage":
            return Effect({"site": [site(a["url"])]})
        case "reserve_hotel":
            return Effect({"vendor": [a["hotel"]], "dates": [f"{a['start_day']}/{a['end_day']}"]})
        case "reserve_restaurant":
            return Effect({"vendor": [a["restaurant"]]})
        case "reserve_car_rental":
            return Effect({"vendor": [a["company"]]})
    return Effect()
