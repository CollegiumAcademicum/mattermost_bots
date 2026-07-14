"""Weekly WG task distributor — DMs each member their tasks for the coming week."""

from __future__ import annotations

import random
from datetime import date

DESCRIPTION = "Verteilt die WG-Aufgaben der nächsten Woche an Konstantin, Simon, Lilly und Philipp"

# Channel ID of the WG group channel for the weekly overview post
WG_CHANNEL_ID = "upt18p5zg3re8r1nb3duhgzr4e"

# Mattermost members: name (for display) + user_id (from Mattermost profile URL or !id)
MEMBERS = [
    {"name": "konstantin_masson ", "user_id": "79ktf4sqsfya8mzb47mrxxkueh"},
    {"name": "simon_bauer",      "user_id": "x463j3kf9jfnppaynyt5wgaoky"},
    {"name": "lillyvappen",      "user_id": "mih8mdc3dtrf3jkq5nd8e1iabo"},
    {"name": "philipp_bartz",    "user_id": "tt63wnfbhjd1dre5r6xmhni93r"},
]

# interval: every N weeks (1=weekly, 2=biweekly, 4=≈monthly)
# offset:   shifts the start week so tasks with the same interval don't all land together
#           due when (week - offset) % interval == 0
# difficulty: 1 (easy) – 3 (hard), used to balance load across members
TASKS = [
    {"name": "Bad Flächen reinigen", "interval": 2, "offset": 0, "difficulty": 2},
    {"name": "Bad Klo, Waschbecken, Spiegel, Armaturen, Abfluss reinigen", "interval": 1, "offset": 0, "difficulty": 2},
    {"name": "Bad Regale putzen", "interval": 2, "offset": 0, "difficulty": 2},
    {"name": "Badlüfter", "interval": 11, "offset": 0, "difficulty": 1},
    {"name": "Küche Oberflächen und Herd im Blick behalten und bei Bedarf nachhelfen, Tisch sauber machen und Wachs entfernen, Müll im Blick haben", "interval": 1, "offset": 0, "difficulty": 1},
    {"name": "Spülmaschienen Maintenance (Filter/Sieb Säubern, Spülmaschienenreiniger und Salz auffüllen)", "interval": 2, "offset": 1, "difficulty": 1},
    {"name": "Spüle deep clean", "interval": 2, "offset": 1, "difficulty": 1},
    {"name": "Küche Frontflächen und Griffe wischen (auch Kühlschrank)", "interval": 1, "offset": 0, "difficulty": 1},
    {"name": "Backofen deep clean", "interval": 8, "offset": 3, "difficulty": 2},
    {"name": "Kühlschrank putzen", "interval": 7, "offset": 4, "difficulty": 3},
    {"name": "Küche Schubladen saugen", "interval": 4, "offset": 6, "difficulty": 1},
    {"name": "Dunstabzugshaube", "interval": 11, "offset": 3, "difficulty": 1},
    {"name": "Boden Wischen", "interval": 1, "offset": 0, "difficulty": 2},
    {"name": "Boden Saugen", "interval": 1, "offset": 0, "difficulty": 1},
    {"name": "Regale abstauben/wischen", "interval": 8, "offset": 0, "difficulty": 2},
    {"name": "Fenster putzen", "interval": 6, "offset": 2, "difficulty": 3},
    {"name": "Lichtschalter, Steckdosen, Türklinke putzen", "interval": 4, "offset": 6, "difficulty": 1},
    {"name": "Sofa saugen", "interval": 3, "offset": 1, "difficulty": 2},
    {"name": "Teppich ausklopfen", "interval": 8, "offset": 6, "difficulty": 3},
]


def _due_tasks(week: int) -> list[dict]:
    return [t for t in TASKS if (week - int(t["offset"])) % int(t["interval"]) == 0]


def _assign(tasks: list[dict], members: list[dict]) -> dict[str, list[dict]]:
    """Greedy bin-packing balanced by difficulty."""
    shuffled = list(tasks)
    random.shuffle(shuffled)
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


_EPOCH = date(2024, 1, 1)  # Monday of ISO week 1, 2024 — arbitrary fixed start


def _abs_week(d: date) -> int:
    """Weeks since _EPOCH — monotonically increasing, no year-boundary reset."""
    return (d - _EPOCH).days // 7


async def run(driver, args: str = "") -> None:
    today = date.today()
    week = _abs_week(today)
    next_week = week + 1  # script runs Sunday of week N → plan week N+1
    kw = today.isocalendar()[1] + 1  # ISO calendar week for display only

    tasks = _due_tasks(next_week)
    if not tasks:
        return

    assignment = _assign(tasks, MEMBERS)
    bot_id = driver.users.get_user("me")["id"]
    member_by_id = {m["user_id"]: m for m in MEMBERS}

    overview = [f"### **WG-Aufgaben KW {kw}:**"]
    overview.append("Bitte reagiert wenn ihr eure Aufgaben erledigt habt!")
    overview.append("___")

    for user_id, member_tasks in assignment.items():
        if not member_tasks:
            continue
        member = member_by_id[user_id]
        #dm_id = driver.channels.create_direct_message_channel([bot_id, user_id])["id"]
        lines = [f"**Hey {member['name']}, deine WG-Aufgaben für KW {kw}:**"]
        for t in member_tasks:
            lines.append(f"- {t['name']} (Schwierigkeit: {'⭐' * t['difficulty']})")
        #driver.posts.create_post({"channel_id": dm_id, "message": "\n".join(lines)})

        overview.append(f"\n**@{member['name']}:**")
        for t in member_tasks:
            overview.append(f"- {t['name']} (Schwierigkeit: {t['difficulty']})")
        overview.append("___")

    overview.append("")
    overview.append("")
    overview.append(f"`randint: {random.randint(1,1000)}`")

    driver.posts.create_post({"channel_id": WG_CHANNEL_ID, "message": "\n".join(overview)})