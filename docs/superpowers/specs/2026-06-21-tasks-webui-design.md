# Design: Tasks admin UI

**Date:** 2026-06-21
**Status:** Approved

## Goal

Add an "Aufgaben" tab to the existing admin dashboard where BotAdmins can see all discovered tasks, trigger them manually, and edit (add/remove) their cron schedules.

---

## Architecture

Follows the established admin dashboard pattern: new postbot API routes → new Django admin_client methods → Django view → template.

```
Browser
  └─ POST /admin/tasks/ (Django)
       └─ admin_client.run_task() / admin_client.set_task_schedule()
            └─ POST /api/tasks/{name}/run  (postbot FastAPI)
            └─ PUT  /api/tasks/{name}/schedule
```

---

## Postbot API — 3 new endpoints

### `GET /api/tasks`

Returns all tasks discovered by the task runner.

**Response:**
```json
{
  "tasks": [
    {
      "name": "example_task",
      "description": "Sends weekly digest",
      "last_run": "2026-06-21T02:00:00Z",
      "schedule": "0 9 * * 1"
    },
    {
      "name": "cleanup_old_logs",
      "description": "—",
      "last_run": null,
      "schedule": null
    }
  ]
}
```

`last_run` is an ISO-8601 UTC string or `null`. `schedule` is the cron expression from `registry.schedule` or `null`.

Implementation: `get_bot()._task_registry` provides the registry; iterate `registry.all_tasks()`, merge with `registry.schedule`.

---

### `POST /api/tasks/{name}/run`

Manually trigger a task. Fire-and-forget — does not wait for the task to complete.

- **404** if task name not in registry
- **200** `{"ok": true}` immediately after dispatching the asyncio task

Implementation: retrieve `TaskEntry` from registry, schedule `_fire_task(entry, bot._driver, bot._post_fn, bot.config.bot_log_channel_id)` as a background `asyncio.Task` using `asyncio.get_event_loop().create_task(...)`.

---

### `PUT /api/tasks/{name}/schedule`

Set or remove a task's cron schedule, persisting to `scheduler.toml`.

**Request body:**
```json
{"cron": "0 9 * * 1"}   // set schedule
{"cron": null}           // remove schedule
```

**Responses:**
- **404** if task name not in registry
- **422** `{"detail": "Invalid cron expression: ..."}` if `cron` is non-null and `croniter.is_valid()` returns False
- **200** `{"ok": true}` on success

Implementation:
1. Validate with `croniter.is_valid(cron)` (only when cron is non-null).
2. Update `registry.schedule` in-memory (add or delete key).
3. Write the entire `[tasks]` section back to `scheduler_toml_path` using `toml.dump({"tasks": registry.schedule})`.

---

## Django webui

### `services/admin_client.py` — 3 new methods

```python
def get_tasks() -> dict:
    """GET /api/tasks → {"tasks": [...]}"""

def run_task(name: str) -> dict:
    """POST /api/tasks/{name}/run → {"ok": True}"""

def set_task_schedule(name: str, cron: str | None) -> dict:
    """PUT /api/tasks/{name}/schedule → {"ok": True}"""
```

All follow the existing pattern: `requests` call with Bearer token, `raise_for_status()`, return `resp.json()`.

---

### `views/tasks.py`

Single view, `@require_bot_admin` decorated.

**GET** — fetch task list via `admin_client.get_tasks()`, render template. On error: show Django message, render empty task list.

**POST** — two actions dispatched by hidden `action` field:

- `action=run, name=<task>` → call `run_task(name)`, redirect with success/error message
- `action=set_schedule, name=<task>, cron=<expr_or_empty>` → call `set_task_schedule(name, cron or None)`, redirect with success/error message

Both redirect back to the tasks tab after the action.

---

### `urls.py` — 1 new route

```python
path("tasks/", views.tasks.tasks_view, name="tasks"),
```

---

### Template: `templates/admin_dashboard/tasks.html`

Extends `base.html`. Adds "Aufgaben" to the tab bar alongside "Verlauf" and "Konfiguration".

**Table columns:** Name | Beschreibung | Letzter Lauf | Zeitplan (Cron) | (Run button)

**Inline edit UX for the Zeitplan column:**

*Normal state (scheduled task):*
- Cron expression shown in a `<code>` tag with a pencil icon
- Clicking either opens the edit state
- "Entfernen" link visible next to cron (also triggers confirmation)

*Normal state (unscheduled task):*
- "+ Zeitplan hinzufügen" link shown instead

*Edit state (activated by click):*
- Text input pre-filled with current cron (empty for new)
- "Speichern" button and "✕" cancel button
- If scheduled: additional "Entfernen" button

**Cron validation (client-side JS, runs on Speichern click):**
```js
function isValidCron(expr) {
  const fields = expr.trim().split(/\s+/);
  if (fields.length !== 5) return false;
  const f = /^(\*|\d+(-\d+)?(\/\d+)?|\*(\/\d+)?|\d+(,\d+)*)$/;
  return fields.every(field => f.test(field));
}
```
If invalid: show inline error message below the input, do not show confirmation dialog.

**Confirmation dialog (shown after valid cron passes client-side check):**
- Appears inline below the row (not a modal)
- Shows: task name + new cron expression
- Two buttons: "Bestätigen" (submits POST form) and "Abbrechen"
- For "Entfernen": confirmation shows task name + "Zeitplan wird entfernt" (no cron expression shown)

**Empty cron = remove:** Saving an empty cron field is treated as a remove action (sends `cron=null` to the API).

**Server-side 422 errors:** If the API returns 422, the Django view adds a Django error message displayed at the top of the tab.

---

## Tab navigation update

The "Aufgaben" tab link is added to the tab bar in both `history.html` and `config.html` (and the new `tasks.html`) so all three tabs show consistent navigation.

The navbar already has separate "Verlauf" and "Konfiguration" links; no navbar change needed — the "Aufgaben" tab is accessed from within the admin dashboard.

---

## Testing

### Postbot API (`tests/test_api_tasks.py`)

- `GET /api/tasks` returns list with correct fields
- `POST /api/tasks/unknown/run` returns 404
- `POST /api/tasks/{name}/run` returns 200 `{"ok": true}` (mock `_fire_task`)
- `PUT /api/tasks/{name}/schedule` with valid cron: returns 200, updates `registry.schedule`, writes scheduler.toml
- `PUT /api/tasks/{name}/schedule` with invalid cron: returns 422
- `PUT /api/tasks/{name}/schedule` with `cron=null`: removes entry from registry and scheduler.toml

### Django (`tests/test_admin_dashboard.py` — extend existing file)

- GET tasks view renders task list
- POST run action calls `run_task`, redirects
- POST set_schedule action calls `set_task_schedule`, redirects
- Admin client `get_tasks`, `run_task`, `set_task_schedule` methods (mock `requests`)

---

## Out of scope

- Uploading or creating new task `.py` files from the UI
- Showing task output or run history
- Real-time task status (running/idle)
- Cron expression human-readable description in the UI (e.g. "Every Monday at 9:00")
