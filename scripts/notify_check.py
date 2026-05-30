#!/usr/bin/env python3
"""Mum-tracker reminder/alert cron.

Runs on a GitHub Actions schedule. Reads a small, PUBLIC-read slice of the
Firebase Realtime DB (notification config + activity heartbeats only - no
health data) and sends Telegram messages. De-dup state is kept in a committed
JSON file, so the cron needs NO Firebase credentials at all. The only secret is
the Telegram bot token.

Env:
  TELEGRAM_BOT_TOKEN   (required) bot token from BotFather
  DB_URL               (required) Firebase RTDB base URL
  TZ=Europe/London     set by the workflow so 'now'/quiet-hours are local
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

STATE_PATH = os.path.join(os.path.dirname(__file__), "notify-state.json")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
DB_URL = os.environ.get("DB_URL", "").strip().rstrip("/")
MED_CATCHUP_MIN = 90          # still fire a missed slot for up to 90 min
DOSE_GRACE_MIN = 45           # treat a dose this many min before a slot as "taken"


def get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"GET failed {url}: {e}", file=sys.stderr)
        return None


def load_state():
    try:
        with open(STATE_PATH) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("medSent", [])
    s.setdefault("inactiveLastSent", None)
    return s


def save_state(s):
    with open(STATE_PATH, "w") as f:
        json.dump(s, f, indent=2)


def parse_ts(v):
    """Parse 'YYYY-MM-DD HH:MM' (or with T) as naive local time."""
    if not v or not isinstance(v, str):
        return None
    v = v.replace("T", " ")[:16]
    try:
        return datetime.strptime(v, "%Y-%m-%d %H:%M")
    except Exception:
        return None


def in_quiet(now, start, end):
    try:
        start = int(start); end = int(end)
    except Exception:
        return False
    if start == end:
        return False
    h = now.hour
    if start < end:
        return start <= h < end
    return h >= start or h < end          # overnight window


def send_telegram(chat_id, text):
    if not chat_id:
        return False
    data = urllib.parse.urlencode({
        "chat_id": str(chat_id),
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            ok = json.loads(r.read().decode()).get("ok", False)
            if not ok:
                print(f"Telegram not ok for {chat_id}", file=sys.stderr)
            return ok
    except Exception as e:
        print(f"Telegram send failed for {chat_id}: {e}", file=sys.stderr)
        return False


def main():
    if not TOKEN or not DB_URL:
        print("Missing TELEGRAM_BOT_TOKEN or DB_URL - nothing to do.")
        return

    cfg = get_json(f"{DB_URL}/meta/notify.json")
    if not cfg or not cfg.get("enabled"):
        print("Notifications disabled or no config.")
        return

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    quiet = in_quiet(now, cfg.get("quietStart", 22), cfg.get("quietEnd", 7))
    state = load_state()
    changed = False

    med_chat = (cfg.get("medChatId") or "").strip()
    alert_chat = (cfg.get("alertChatId") or "").strip() or med_chat

    last_dose = parse_ts(get_json(f"{DB_URL}/meta/lastDose.json"))
    last_act_raw = get_json(f"{DB_URL}/meta/lastActivity.json")
    last_act = parse_ts(last_act_raw.get("ts")) if isinstance(last_act_raw, dict) else None

    # --- Medication reminders (scheduled times) ---
    if med_chat and not quiet:
        for t in cfg.get("medTimes", []) or []:
            try:
                hh, mm = [int(x) for x in t.split(":")]
            except Exception:
                continue
            slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            key = f"{today}@{t}"
            if key in state["medSent"]:
                continue
            if not (slot <= now <= slot + timedelta(minutes=MED_CATCHUP_MIN)):
                continue
            # Skip if a dose was already logged around/after this slot.
            if last_dose and last_dose >= slot - timedelta(minutes=DOSE_GRACE_MIN):
                state["medSent"].append(key); changed = True
                continue
            if send_telegram(med_chat, cfg.get("medMessage", "Time for meds")):
                state["medSent"].append(key); changed = True

    # keep only today's slot keys
    pruned = [k for k in state["medSent"] if k.startswith(today)]
    if pruned != state["medSent"]:
        state["medSent"] = pruned; changed = True

    # --- Inactivity alert (no logging for a while) ---
    if alert_chat and last_act and not quiet:
        thresh = float(cfg.get("inactivityHours", 8))
        gap_h = (now - last_act).total_seconds() / 3600.0
        if gap_h >= thresh:
            last_sent = parse_ts(state.get("inactiveLastSent"))
            should = (
                last_sent is None
                or last_sent < last_act                                  # new activity since last alert
                or (now - last_sent).total_seconds() / 3600.0 >= thresh  # still silent: re-alert
            )
            if should:
                msg = (f"⚠️ No tracker activity for {gap_h:.1f}h "
                       f"(last log {last_act.strftime('%a %H:%M')}). "
                       f"Please check on mum / log an update.")
                if send_telegram(alert_chat, msg):
                    state["inactiveLastSent"] = now.strftime("%Y-%m-%d %H:%M")
                    changed = True

    if changed:
        save_state(state)
        print("State updated.")
    else:
        print("No notifications sent.")


if __name__ == "__main__":
    main()
