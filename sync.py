#!/usr/bin/env python3
"""
findmy-trail — auto-sync your OWN device's location via iCloud Find My (pyicloud).

Polls the device location every N minutes, writes locations.json, optionally
syncs to your own private GitHub repo, and serves the tracker locally.

⚠️  ETHICAL USE: only use this with an Apple ID you own and devices you are
    authorised to locate. Tracking someone without consent may be illegal.

Setup:
    pip install pyicloud
    python sync.py

On first run it asks for your Apple ID + password (stored locally only) and,
if cloud sync is configured, your GitHub token. 2FA is handled interactively.
See README.md for configuration (environment variables).
"""

import json
import os
import sys
import time
import base64
import threading
import http.server
import webbrowser
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
LOCATIONS_FILE = SCRIPT_DIR / "locations.json"
SESSION_DIR = SCRIPT_DIR / ".icloud_session"
TOKEN_FILE = SESSION_DIR / "gh_token.txt"   # gitignored — never committed
POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "10"))
PORT = int(os.environ.get("PORT", "8080"))

# ── Your config — set via environment variables (or edit the defaults) ──
# GitHub repo that holds your shared locations.json (optional two-way cloud sync).
# Point this at YOUR OWN PRIVATE repo. Leave as placeholders to skip cloud sync.
GH_OWNER  = os.environ.get("GH_OWNER",  "YOUR_GITHUB_USERNAME")
GH_REPO   = os.environ.get("GH_REPO",   "YOUR_PRIVATE_REPO")
GH_PATH   = os.environ.get("GH_PATH",   "locations.json")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")

# Push alerts via ntfy.sh (free, no signup). Subscribe to this exact topic
# in the ntfy app on your phone to get an instant alert when the device comes online.
# Pick your own hard-to-guess topic string.
NTFY_TOPIC   = os.environ.get("NTFY_TOPIC", "")          # e.g. "findmytrail-9f3k2x7q"
NTFY_ENABLED = bool(NTFY_TOPIC)                            # alerts on only if a topic is set

# ── helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_locations():
    if LOCATIONS_FILE.exists():
        try:
            return json.loads(LOCATIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_locations(locs):
    LOCATIONS_FILE.write_text(json.dumps(locs, indent=2, ensure_ascii=False), encoding="utf-8")

# ── Alerts + reverse geocoding ────────────────────────────────────────────────

def reverse_geocode(lat, lng):
    """Free reverse geocoding via OpenStreetMap Nominatim. Returns a short address or ''."""
    url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode({
        "lat": lat, "lon": lng, "format": "json", "zoom": "16"
    })
    req = urllib.request.Request(url, headers={"User-Agent": "findmy-trail/1.0", "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        a = data.get("address", {})
        parts = [a.get("road"), a.get("suburb"), a.get("city_district"),
                 a.get("city") or a.get("town") or a.get("village")]
        return ", ".join([p for p in parts if p][:3])
    except Exception:
        return ""

def notify(title, message, lat=None, lng=None, priority="urgent"):
    """Send a push alert to the phone via ntfy.sh (no account needed)."""
    if not NTFY_ENABLED:
        return
    try:
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": priority,
            "Tags": "rotating_light",
        }
        if lat is not None and lng is not None:
            # Tapping the notification opens Google Maps at the spot
            headers["Click"] = f"https://www.google.com/maps?q={lat},{lng}"
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        log("Alert sent to phone.")
    except Exception as e:
        log(f"Alert failed: {e}")

# ── GitHub cloud sync (two-way, same store the phone uses) ─────────────────────

_gh_token_cache = None

def gh_token():
    """Token from env GH_TOKEN, or .icloud_session/gh_token.txt, else prompt once."""
    global _gh_token_cache
    if _gh_token_cache:
        return _gh_token_cache
    tok = os.environ.get("GH_TOKEN", "").strip()
    if not tok and TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not tok:
        print("\n  Cloud sync token (same one you paste into the phone app).")
        print("  Leave blank to fall back to plain 'git push'.\n")
        tok = input("  GitHub sync token: ").strip()
        if tok:
            SESSION_DIR.mkdir(exist_ok=True)
            TOKEN_FILE.write_text(tok, encoding="utf-8")
    _gh_token_cache = tok
    return tok

def _gh_request(method, url, body=None):
    headers = {
        "Authorization": "Bearer " + gh_token(),
        "Accept": "application/vnd.github+json",
        "User-Agent": "findmy-trail",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def cloud_get():
    """Returns (points_list, sha). sha is None if file doesn't exist yet."""
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{GH_PATH}?ref={GH_BRANCH}&_={int(time.time())}"
    try:
        data = _gh_request("GET", url)
        content = base64.b64decode(data.get("content", "")).decode("utf-8")
        return (json.loads(content) if content.strip() else []), data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return [], None
        raise

def cloud_put(points_list, sha, message):
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{GH_PATH}"
    body = {
        "message": message,
        "content": base64.b64encode(json.dumps(points_list, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii"),
        "branch": GH_BRANCH,
    }
    if sha:
        body["sha"] = sha
    data = _gh_request("PUT", url, body)
    return data.get("content", {}).get("sha")

def merge_points(base, incoming):
    """Union by id; last-write-wins via updatedAt. Returns merged list."""
    by_id = {}
    for p in base + incoming:
        pid = p.get("id")
        if pid is None:
            pid = int(datetime.fromisoformat(p["time"]).timestamp() * 1000) if p.get("time") else int(time.time() * 1000)
            p["id"] = pid
        if pid not in by_id or (p.get("updatedAt", 0) or 0) > (by_id[pid].get("updatedAt", 0) or 0):
            by_id[pid] = p
    return list(by_id.values())

def cloud_sync_new_point(point):
    """Pull cloud, merge the new auto-point, push back, and update local file.
    Falls back to plain git push if no token is configured."""
    if not gh_token():
        save_locations(load_locations())  # ensure local written
        _git_push_fallback(f"Location update {point['time']}")
        return

    for attempt in range(3):
        try:
            remote, sha = cloud_get()
            merged = merge_points(remote, [point])
            merged.sort(key=lambda p: p.get("time", ""))
            cloud_put(merged, sha, f"Location update {point['time']}")
            save_locations(merged)  # keep local file in sync for the read-only fallback
            log("Synced to cloud.")
            return
        except urllib.error.HTTPError as e:
            if e.code in (409, 422) and attempt < 2:
                continue  # sha conflict — retry with fresh sha
            log(f"Cloud sync error: HTTP {e.code}")
            return
        except Exception as e:
            log(f"Cloud sync error: {e}")
            return

def cloud_pull_to_local():
    """Pull the latest cloud state into the local file (so the local browser sees phone edits)."""
    if not gh_token():
        return
    try:
        remote, _ = cloud_get()
        merged = merge_points(load_locations(), remote)
        merged.sort(key=lambda p: p.get("time", ""))
        save_locations(merged)
    except Exception as e:
        log(f"Cloud pull error: {e}")

def _git_push_fallback(message="Location update"):
    try:
        subprocess.run(["git", "add", "locations.json"], cwd=str(SCRIPT_DIR), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], cwd=str(SCRIPT_DIR), check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=str(SCRIPT_DIR), check=True, capture_output=True)
        log("Pushed to GitHub (git).")
    except subprocess.CalledProcessError:
        pass

def fmt_time(ts):
    """Round datetime to nearest minute for dedup key."""
    return ts.strftime("%Y-%m-%dT%H:%M")

# ── iCloud auth ───────────────────────────────────────────────────────────────

def connect_icloud():
    try:
        from pyicloud import PyiCloudService
        from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudAPIResponseException
    except ImportError:
        print("\n  pyicloud is not installed. Run:\n  pip install pyicloud\n")
        sys.exit(1)

    SESSION_DIR.mkdir(exist_ok=True)
    creds_file = SESSION_DIR / "creds.json"

    if creds_file.exists():
        creds = json.loads(creds_file.read_text())
        apple_id = creds["apple_id"]
        password = creds["password"]
        log(f"Using saved Apple ID: {apple_id}")
    else:
        print("\n  Enter your girlfriend's iCloud credentials.")
        print("  (stored locally in .icloud_session/ — never sent anywhere else)\n")
        apple_id = input("  Apple ID (email): ").strip()
        password = input("  Password: ").strip()
        creds_file.write_text(json.dumps({"apple_id": apple_id, "password": password}))

    try:
        api = PyiCloudService(apple_id, password, cookie_directory=str(SESSION_DIR))
    except PyiCloudFailedLoginException:
        log("Login failed. Check credentials.")
        if creds_file.exists():
            creds_file.unlink()
        sys.exit(1)

    # Handle 2FA
    if api.requires_2fa:
        print("\n  Two-factor authentication required.")
        print("  Check the trusted device or SMS for the code.\n")
        code = input("  Enter 2FA code: ").strip()
        result = api.validate_2fa_code(code)
        if not result:
            log("2FA code rejected.")
            sys.exit(1)
        log("2FA verified.")
    elif api.requires_2sa:
        print("\n  Two-step verification required.")
        devices = api.trusted_devices
        for i, d in enumerate(devices):
            print(f"  [{i}] {d.get('deviceName', 'SMS to ' + d.get('phoneNumber', '?'))}")
        idx = int(input("  Choose device: ").strip())
        device = devices[idx]
        if not api.send_verification_code(device):
            log("Failed to send verification code.")
            sys.exit(1)
        code = input("  Enter code: ").strip()
        if not api.validate_verification_code(device, code):
            log("Code rejected.")
            sys.exit(1)
        log("2-step verified.")

    return api

# ── device selection ──────────────────────────────────────────────────────────

def device_attr(d, key, default=""):
    """Safely get an attribute from an AppleDevice (handles both old dict-style and new class-style pyicloud)."""
    try:
        return d[key]
    except (KeyError, TypeError):
        pass
    try:
        return getattr(d, key, default)
    except Exception:
        return default

def pick_device(api):
    devices = list(api.devices)
    if not devices:
        log("No devices found on this account.")
        sys.exit(1)

    print("\n  Devices on this account:")
    for i, d in enumerate(devices):
        name  = device_attr(d, "name", f"Device {i}")
        model = device_attr(d, "deviceDisplayName", "")
        print(f"  [{i}] {name}  ({model})")

    if len(devices) == 1:
        choice = 0
    else:
        choice = int(input("\n  Select device number to track: ").strip())

    device = devices[choice]
    log(f"Tracking: {device_attr(device, 'name', 'selected device')}")
    return choice

# ── poll loop ─────────────────────────────────────────────────────────────────

def poll_once(device):
    try:
        # The device payload is a dict; live GPS lives under "location",
        # offline-network location (when readable) under "trackingInfo".
        raw = None
        for attr in ["data", "content", "_data", "status"]:
            try:
                raw = getattr(device, attr, None)
                if raw:
                    break
            except Exception:
                pass

        if raw and isinstance(raw, dict):
            loc = raw.get("location")
            if not loc:
                tracking = raw.get("trackingInfo")
                if isinstance(tracking, dict):
                    loc = (tracking.get("location") or
                           tracking.get("cachedLocation") or
                           tracking.get("lastLocation"))
        else:
            loc = device.location
            if callable(loc):
                loc = loc()

    except Exception as e:
        log(f"Location fetch error: {e}")
        return None

    if not loc:
        log("Phone offline — no location yet. Will alert the moment it comes online.")
        return None

    # loc can be a dict or an object — handle both
    def get_loc(key, default=None):
        try:
            return loc[key]
        except (KeyError, TypeError):
            return getattr(loc, key, default)

    lat      = get_loc("latitude")
    lng      = get_loc("longitude")
    ts_unix  = (get_loc("timeStamp") or 0) / 1000
    accuracy = get_loc("horizontalAccuracy", None)

    if not lat or not lng:
        log("Location data incomplete — skipping.")
        return None

    # Battery (0..1 float) + charging status, read off the device object
    batt_level = device_attr(device, "batteryLevel", None)
    batt_status = device_attr(device, "batteryStatus", None)
    try:
        batt_pct = round(float(batt_level) * 100) if batt_level not in (None, "") else None
    except Exception:
        batt_pct = None

    ts = datetime.fromtimestamp(ts_unix) if ts_unix > 0 else datetime.now()
    return {
        "lat": lat, "lng": lng, "time": fmt_time(ts),
        "accuracy_m": round(accuracy) if isinstance(accuracy, (int, float)) else None,
        "battery": batt_pct,
        "batteryStatus": batt_status,
    }

def run_sync(api, device_index):
    log(f"Polling every {POLL_INTERVAL_MINUTES} min. Press Ctrl+C to stop.")
    log(f"Open tracker: http://localhost:{PORT}/tracker.html")

    while True:
        # Re-fetch devices each cycle to get fresh location data
        try:
            devices = list(api.devices)
            device = devices[device_index]
        except Exception as e:
            log(f"Device refresh error: {e}")
            time.sleep(POLL_INTERVAL_MINUTES * 60)
            continue

        # Always pull cloud first so the local file reflects phone edits
        cloud_pull_to_local()

        result = poll_once(device)
        if result:
            locations = load_locations()
            existing_times = {p["time"] for p in locations}

            if result["time"] not in existing_times:
                now_ms = int(time.time() * 1000)
                acc = result.get("accuracy_m")
                addr = reverse_geocode(result["lat"], result["lng"])
                point = {
                    "lat": result["lat"],
                    "lng": result["lng"],
                    "time": result["time"],
                    "note": "Auto-synced" + (f" (±{acc}m)" if acc else ""),
                    "id": now_ms,
                    "updatedAt": now_ms,
                    "address": addr or None,
                    "accuracy": acc,
                    "battery": result.get("battery"),
                    "batteryStatus": result.get("batteryStatus"),
                }
                log(f"New point: {result['lat']:.5f}, {result['lng']:.5f} at {result['time']}"
                    + (f" | battery {result['battery']}% {result.get('batteryStatus') or ''}" if result.get('battery') is not None else ""))
                cloud_sync_new_point(point)

                # 🔔 Alert: the phone is ONLINE and reporting a location
                batt = f"\nBattery: {result['battery']}% ({result.get('batteryStatus') or '?'})" if result.get("battery") is not None else ""
                where = addr or f"{result['lat']:.5f}, {result['lng']:.5f}"
                notify(
                    "📍 Phone is ONLINE",
                    f"Location: {where}{batt}\nAccuracy: ±{acc}m" if acc else f"Location: {where}{batt}",
                    lat=result["lat"], lng=result["lng"],
                )
            else:
                log(f"No change since last update ({result['time']})")

        time.sleep(POLL_INTERVAL_MINUTES * 60)

# ── HTTP server ───────────────────────────────────────────────────────────────

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SCRIPT_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # silence request logs

    def end_headers(self):
        # Allow the page to fetch locations.json
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

def start_server():
    server = http.server.HTTPServer(("localhost", PORT), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log(f"Local server running at http://localhost:{PORT}")

# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Stolen Phone Tracker — iCloud Auto-Sync")
    print("=" * 55)

    # Ensure locations.json exists
    if not LOCATIONS_FILE.exists():
        save_locations([])

    start_server()

    api = connect_icloud()
    device_index = pick_device(api)

    # Open browser automatically
    time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}/tracker.html")

    try:
        run_sync(api, device_index)
    except KeyboardInterrupt:
        print("\nStopped.")
