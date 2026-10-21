"""Generate a synthetic IT support ticket dataset.

The dataset lets the project run out of the box. For real accuracy numbers,
train on a public dataset instead (see README, "Train on a real dataset").

Usage:
    python scripts/generate_tickets.py --n 2000 --out data/tickets.csv
"""
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Each issue: (category, title templates, description templates, typical priority weights H/M/L)
ISSUES = {
    "Network": [
        (["VPN not connecting", "VPN keeps disconnecting", "Cannot connect to VPN from home"],
         ["The VPN client says connection failed when I try to connect from home.",
          "VPN drops every few minutes and I lose access to the intranet.",
          "I can't reach internal sites because the VPN won't connect."], (3, 5, 2)),
        (["Wi-Fi not working on floor {floor}", "No internet on office Wi-Fi", "Cannot connect to CORP-SECURE"],
         ["My laptop does not connect to the office Wi-Fi on floor {floor}.",
          "Wi-Fi shows connected but no internet access in the {building} building.",
          "Several people near me lost wifi connection this morning."], (4, 4, 2)),
        (["Shared drive not accessible", "Network drive missing", "Slow network in office"],
         ["The mapped network drive is not opening and says the path is unavailable.",
          "Network is very slow, file transfers to the shared drive take ages.",
          "I cannot access the team share on the file server."], (2, 5, 3)),
    ],
    "Access": [
        (["Password reset needed", "Forgot my password", "Password expired"],
         ["I forgot my password and cannot log in to my laptop.",
          "My password expired and the self-service reset portal is not working.",
          "Need to reset my password, locked out after holiday."], (3, 5, 2)),
        (["Account locked out", "Account keeps getting locked", "Locked out of my account"],
         ["My account is locked after too many failed attempts.",
          "Account keeps locking every hour even after I changed the password.",
          "I cannot sign in, it says the account is locked."], (5, 4, 1)),
        (["MFA not working", "New phone MFA reset", "Not receiving MFA prompts"],
         ["I got a new phone and need the authenticator MFA reset.",
          "The MFA push notification is not arriving on my phone.",
          "Authenticator app codes are being rejected at sign in."], (4, 4, 2)),
        (["Access request for application", "Need access to SharePoint site", "New joiner access"],
         ["Please grant me access to the finance reporting application.",
          "I need permission to the project SharePoint site, owner has approved.",
          "New joiner starting Monday needs account and email access."], (1, 5, 4)),
    ],
    "Hardware": [
        (["Printer not working", "Cannot print", "Printer paper jam"],
         ["The printer on floor {floor} shows a paper jam and won't print.",
          "My print jobs are stuck in the queue and nothing comes out.",
          "Secure print does not release my documents when I tap my badge."], (1, 4, 5)),
        (["Laptop very slow", "Laptop overheating", "Laptop battery draining fast"],
         ["My laptop is extremely slow and freezes when opening Excel.",
          "Laptop fan is very loud and the laptop gets hot.",
          "Battery drains within an hour even when fully charged."], (2, 5, 3)),
        (["Laptop stolen", "Lost laptop", "Lost company phone"],
         ["My laptop was stolen from my car, need it locked and replaced.",
          "I lost my company phone while travelling.",
          "Laptop bag was lost at the airport including the laptop."], (8, 2, 0)),
        (["Monitor not detected", "Docking station not working", "Keyboard not working"],
         ["External monitor is not detected when I connect the docking station.",
          "The docking station does not charge my laptop anymore.",
          "Keyboard keys stopped working, need a replacement."], (1, 4, 5)),
        (["Disk space full", "Low disk space warning", "C drive full"],
         ["I am getting low disk space warnings and cannot save files.",
          "C drive is 98% full and the laptop is very slow.",
          "Disk is full, cannot install updates."], (2, 5, 3)),
    ],
    "Software": [
        (["Software installation request", "Need Python installed", "Install request for VS Code"],
         ["Please install {app} on my laptop for project work.",
          "{app} is not available in Software Center, can you install it?",
          "Need {app} installed, I do not have admin rights."], (1, 4, 5)),
        (["Teams audio not working", "Teams camera not working", "Teams crashing"],
         ["Nobody can hear me in Teams calls, microphone not working.",
          "Camera shows black screen in Teams meetings.",
          "Teams crashes every time I join a meeting."], (3, 5, 2)),
        (["OneDrive not syncing", "OneDrive sync error", "Files not uploading to OneDrive"],
         ["OneDrive shows a sync error and my files are not uploading.",
          "OneDrive is paused and won't resume syncing.",
          "Changes I make are not syncing to OneDrive."], (2, 5, 3)),
        (["Excel crashing", "Application not responding", "License expired error"],
         ["Excel crashes when I open large files.",
          "The application stops responding after the latest update.",
          "{app} says my license has expired."], (2, 5, 3)),
    ],
    "Email": [
        (["Outlook not syncing", "Not receiving emails", "Outlook disconnected"],
         ["Outlook is not receiving new emails since this morning.",
          "Outlook shows disconnected and emails are stuck in the outbox.",
          "Emails are not syncing between Outlook and my phone."], (4, 4, 2)),
        (["Shared mailbox access", "Need access to shared mailbox", "Send as permission"],
         ["Please give me access to the team shared mailbox.",
          "I need send as permission on the support mailbox.",
          "Shared mailbox is not showing in Outlook after approval."], (1, 5, 4)),
        (["Phishing email received", "Suspicious email", "Clicked on phishing link"],
         ["I received a suspicious email asking for my password.",
          "I clicked a link in a phishing email and entered my credentials.",
          "Got an email asking to buy gift cards for the CEO."], (6, 3, 1)),
        (["Mailbox full", "Mailbox quota exceeded", "Cannot send email"],
         ["My mailbox is full and I cannot send emails.",
          "Getting quota exceeded warnings in Outlook.",
          "Emails bounce back saying the mailbox is full."], (3, 5, 2)),
    ],
}

PRIORITIES = ["High", "Medium", "Low"]
UP_CUES = ["This is urgent.", "Need this fixed before my meeting.", "Whole team is blocked.",
           "Customer demo in an hour.", "I cannot work at all."]
DOWN_CUES = ["No rush.", "Whenever someone is free.", "There is a workaround for now.",
             "Colleagues are not affected."]
FILLERS = ["", "", "Please help.", "Thanks in advance.", "It started after the latest update.",
           "Restarting did not help."] + UP_CUES + DOWN_CUES
APPS = ["Python", "VS Code", "Power BI Desktop", "Tableau", "Postman", "Docker Desktop", "MATLAB"]
BUILDINGS = ["Whitefield", "Tower A", "Tower B", "Manyata"]


def make_ticket(rng: random.Random, ticket_id: int, start: datetime, days: int, noise: float):
    category = rng.choice(list(ISSUES))
    titles, descs, weights = rng.choice(ISSUES[category])
    fmt = {"floor": rng.randint(1, 8), "app": rng.choice(APPS), "building": rng.choice(BUILDINGS)}
    title = rng.choice(titles).format(**fmt)
    description = (rng.choice(descs).format(**fmt) + " " + rng.choice(FILLERS)).strip()
    priority = rng.choices(PRIORITIES, weights=weights)[0]
    # Urgency cues in the text move the priority, like a real service desk would.
    if any(cue in description for cue in UP_CUES):
        priority = PRIORITIES[max(0, PRIORITIES.index(priority) - 1)]
    elif any(cue in description for cue in DOWN_CUES):
        priority = PRIORITIES[min(2, PRIORITIES.index(priority) + 1)]

    # Label noise: real ticket data is messy and sometimes mis-categorised.
    if rng.random() < noise:
        category = rng.choice(list(ISSUES))

    created = start + timedelta(days=rng.random() * days)
    status = "Resolved" if rng.random() < 0.78 else "Open"
    resolved_at, by_bot = "", False
    if status == "Resolved":
        hours = {"High": 4, "Medium": 18, "Low": 40}[priority]
        resolved_at = (created + timedelta(hours=rng.expovariate(1 / hours))).isoformat(timespec="seconds")
        by_bot = rng.random() < 0.35
    return {
        "id": ticket_id, "title": title, "description": description,
        "category": category, "priority": priority, "status": status,
        "created_at": created.isoformat(timespec="seconds"),
        "resolved_at": resolved_at, "resolved_by_bot": int(by_bot),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--noise", type=float, default=0.06)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "tickets.csv"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    start = datetime(2026, 8, 1, 9, 0, 0)
    rows = sorted((make_ticket(rng, i + 1, start, args.days, args.noise) for i in range(args.n)),
                  key=lambda r: r["created_at"])
    for i, r in enumerate(rows, 1):
        r["id"] = i
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} tickets to {args.out}")


if __name__ == "__main__":
    main()
