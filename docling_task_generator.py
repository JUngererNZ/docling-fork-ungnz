from pathlib import Path
from datetime import datetime, timedelta
import json
import random
import string

# ==========================================================
# CONFIG
# ==========================================================

KB_FILE = Path(
    r"C:\Users\Jason\OneDrive - FML Freight Solutions\Microsoft Copilot Chat Files\_json_output\knowledge_base.jsonl"
)

TASK_FILE = Path(
    r"C:\Users\Jason\OneDrive - FML Freight Solutions\Microsoft Copilot Chat Files\_json_output\task_register.json"
)

TASK_HISTORY = Path(
    r"C:\Users\Jason\OneDrive - FML Freight Solutions\Microsoft Copilot Chat Files\_json_output\task_history.json"
)

TASK_SUMMARY = Path(
    r"C:\Users\Jason\OneDrive - FML Freight Solutions\Microsoft Copilot Chat Files\_json_output\task_summary.json"
)

REVIEW_DAYS = 3

# ==========================================================
# TASK RULES
# ==========================================================

RULES = {

    "pod": {
        "task": "Obtain Proof of Delivery (POD)",
        "priority": "HIGH"
    },

    "proof of delivery": {
        "task": "Obtain Proof of Delivery (POD)",
        "priority": "HIGH"
    },

    "acquittal": {
        "task": "Verify Acquittal",
        "priority": "HIGH"
    },

    "action required": {
        "task": "Review Action Required Item",
        "priority": "HIGH"
    },

    "invoice": {
        "task": "Verify Client Invoice",
        "priority": "MEDIUM"
    },

    "payment": {
        "task": "Verify Payment Status",
        "priority": "MEDIUM"
    },

    "awaiting": {
        "task": "Review Awaiting Item",
        "priority": "MEDIUM"
    },

    "claim": {
        "task": "Review Claim Status",
        "priority": "MEDIUM"
    },

    "eta": {
        "task": "Verify ETA",
        "priority": "LOW"
    },

    "blocked": {
        "task": "Review Blocked File",
        "priority": "HIGH"
    },

    "overdue": {
        "task": "Resolve Overdue Item",
        "priority": "HIGH"
    }
}

# ==========================================================
# HELPERS
# ==========================================================

def now():

    return datetime.now()


def generate_guid():

    chars = string.ascii_uppercase + string.digits

    return "".join(
        random.choice(chars)
        for _ in range(5)
    )


def generate_task_id(file_ref):

    if file_ref:

        prefix = (
            file_ref
            .replace(" ", "")
            [:5]
        )

    else:

        prefix = "FILE"

    return (
        prefix
        + "-"
        + generate_guid()
    )


def load_json(path):

    if path.exists():

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    return []


def save_json(path, data):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

# ==========================================================
# LOAD EXISTING TASKS
# ==========================================================

existing_tasks = load_json(
    TASK_FILE
)

task_history = load_json(
    TASK_HISTORY
)

existing_keys = {

    (
        t.get("file_ref"),
        t.get("task")
    )

    for t in existing_tasks
}

# ==========================================================
# UPDATE EXISTING TASKS
# ==========================================================

today = now()

for task in existing_tasks:

    review_date = datetime.fromisoformat(
        task["review_date"]
    )

    age_days = (
        today - review_date
    ).days

    # default

    if task["status"] == "COMPLETED":
        continue

    # open

    task["status"] = "OPEN"

    if today >= review_date:

        task["status"] = "REVIEW_DUE"

    if age_days >= 3:

        task["status"] = "OVERDUE"

    if age_days >= 7:

        task["status"] = "ESCALATE"

# ==========================================================
# SCAN KNOWLEDGE BASE
# ==========================================================

new_tasks = []

with open(
    KB_FILE,
    "r",
    encoding="utf-8"
) as f:

    for line in f:

        try:

            record = json.loads(
                line
            )

        except:

            continue

        text = (
            record.get(
                "chunk_text",
                ""
            )
            .lower()
        )

        file_ref = record.get(
            "file_ref"
        )

        pin = record.get(
            "pin"
        )

        document_id = record.get(
            "document_id"
        )

        source_file = record.get(
            "source_file"
        )

        document_json = record.get(
            "document_json"
        )

        for trigger, rule in RULES.items():

            if trigger not in text:
                continue

            unique_key = (
                file_ref,
                rule["task"]
            )

            if (
                unique_key
                in existing_keys
            ):
                continue

            task = {

                "task_id":
                    generate_task_id(
                        file_ref
                    ),

                "file_ref":
                    file_ref,

                "pin":
                    pin,

                "document_id":
                    document_id,

                "source_file":
                    source_file,

                "document_json":
                    document_json,

                "task":
                    rule["task"],

                "trigger":
                    trigger,

                "priority":
                    rule["priority"],

                "status":
                    "OPEN",

                "created":
                    today.isoformat(),

                "review_date":

                    (
                        today
                        + timedelta(
                            days=REVIEW_DAYS
                        )
                    ).isoformat(),

                "last_reviewed":
                    None,

                "completed_date":
                    None
            }

            new_tasks.append(
                task
            )

            existing_keys.add(
                unique_key
            )

# ==========================================================
# MERGE TASKS
# ==========================================================

all_tasks = (
    existing_tasks
    + new_tasks
)

# ==========================================================
# TASK HISTORY
# ==========================================================

task_history.append({

    "run_date":
        today.isoformat(),

    "new_tasks":
        len(new_tasks),

    "total_tasks":
        len(all_tasks)
})

# ==========================================================
# SUMMARY STATS
# ==========================================================

summary = {

    "generated":
        today.isoformat(),

    "total_tasks":
        len(all_tasks),

    "open":
        len([
            t
            for t in all_tasks
            if t["status"] == "OPEN"
        ]),

    "review_due":
        len([
            t
            for t in all_tasks
            if t["status"]
            == "REVIEW_DUE"
        ]),

    "overdue":
        len([
            t
            for t in all_tasks
            if t["status"]
            == "OVERDUE"
        ]),

    "escalate":
        len([
            t
            for t in all_tasks
            if t["status"]
            == "ESCALATE"
        ]),

    "completed":
        len([
            t
            for t in all_tasks
            if t["status"]
            == "COMPLETED"
        ])
}

# ==========================================================
# SAVE OUTPUTS
# ==========================================================

save_json(
    TASK_FILE,
    all_tasks
)

save_json(
    TASK_HISTORY,
    task_history
)

save_json(
    TASK_SUMMARY,
    summary
)

# ==========================================================
# PRINT
# ==========================================================

print("=" * 80)
print("TASK GENERATION COMPLETE")
print("=" * 80)

print(f"New Tasks      : {len(new_tasks)}")
print(f"Total Tasks    : {summary['total_tasks']}")
print(f"Open           : {summary['open']}")
print(f"Review Due     : {summary['review_due']}")
print(f"Overdue        : {summary['overdue']}")
print(f"Escalate       : {summary['escalate']}")
print(f"Completed      : {summary['completed']}")
print("=" * 80)

print()
print(f"Task Register : {TASK_FILE}")
print(f"Task History  : {TASK_HISTORY}")
print(f"Task Summary  : {TASK_SUMMARY}")