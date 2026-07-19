"""Weekly WG task distributor — DMs each member their tasks for the coming week."""

from __future__ import annotations

import random
from datetime import date

import requests


DESCRIPTION = "Verteilt die WG-Aufgaben der nächsten Woche an die WG 3.10"

FILE_URL = "https://cacloud.ca-hd.de/index.php/s/dFaLPwzYFy9BAxF/download"
# JSON shape: {"wg_channel_id": "...", "members": [...], "tasks": [...]}


def get_infos() -> tuple[str, list[dict], list[dict]]:
    resp = requests.get(FILE_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data["wg_channel_id"], data["members"], data["tasks"]

def _due_tasks(week: int, tasks: list[dict[str, str|int]]) -> list[dict]:
    return [t for t in tasks if (week - int(t["offset"])) % int(t["interval"]) == 0]


def _assign(tasks: list[dict], members: list[dict]) -> dict[str, list[dict]]:
    """Greedy bin-packing balanced by difficulty."""
    shuffled = list(tasks)
    random.shuffle(shuffled)
    random.shuffle(members)
    # stable sort keeps shuffled order for ties → different assignment each week
    shuffled.sort(key=lambda t: -t["difficulty"])

    keys = [m["user_id"] for m in members]
    load = {k: 0 for k in keys}
    assigned: dict[str, list[dict]] = {k: [] for k in keys}
    for task in shuffled:
        lightest = min(keys, key=lambda k: load[k])
        assigned[lightest].append(task)
        load[lightest] += task["difficulty"]
    return assigned


_EPOCH = date(2023, 2, 17)  #  fixed start, date of ersteinzug CA, erste Schlüsselübergaben


def _abs_week(d: date) -> int:
    """Weeks since _EPOCH — monotonically increasing, no year-boundary reset."""
    return (d - _EPOCH).days // 7


async def run(driver, args: str = "") -> None:
    today = date.today()
    week = _abs_week(today)
    next_week = week + 1  # script runs Sunday of week N → plan week N+1
    kw = today.isocalendar()[1] + 1  # ISO calendar week for display only

    wg_channel_id, members, tasks = get_infos()

    tasks = _due_tasks(next_week, tasks)
    if not tasks:
        return

    assignment = _assign(tasks, members)
    bot_id = driver.users.get_user("me")["id"]
    member_by_id = {m["user_id"]: m for m in members}

    overview = [f"### **WG-Aufgaben KW {kw}:**"]
    overview.append("Bitte reagiert wenn ihr eure Aufgaben erledigt habt!")
    overview.append("___")

    for user_id, member_tasks in assignment.items():
        if not member_tasks:
            continue
        member = member_by_id[user_id]

        overview.append(f"\n**@{member['name']}:**")
        for t in member_tasks:
            overview.append(f"- {t['name']} (Schwierigkeit: {t['difficulty']})")
        overview.append("___")

    overview.append("")
    overview.append("")
    overview.append(f"`randint: {random.randint(1,1000)}`")

    driver.posts.create_post({"channel_id": wg_channel_id, "message": "\n".join(overview)})


if __name__ == "__main__":
    print(get_infos())