#!/usr/bin/env python3
"""
Generate clean README/landing screenshots from sample data — no real data used.

One-time setup:
    pip install playwright
    playwright install chromium

Run:
    python tools/make_screenshots.py

Outputs:
    docs/trail-map.png   (desktop map + trail + hotspot)
    docs/mobile.png      (mobile Trail tab with Patterns open)
    docs/report.png      (report.html)

It temporarily swaps in fake data, captures, then restores your locations.json.
"""
import json, shutil, threading, time, functools, http.server, socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"; DOCS.mkdir(exist_ok=True)
LOC = ROOT / "locations.json"
BACKUP = ROOT / "locations.json.bak"
PORT = 8099

FAKE = [
    {"lat":3.1390,"lng":101.6869,"time":"2026-01-10T19:30","note":"Auto-synced","id":1,"updatedAt":1,"address":"KLCC, Kuala Lumpur","accuracy":25,"battery":78,"batteryStatus":"NotCharging"},
    {"lat":3.1468,"lng":101.6936,"time":"2026-01-10T20:10","note":"Auto-synced","id":2,"updatedAt":1,"address":"Jalan Ampang, KL","accuracy":60,"battery":71,"batteryStatus":"NotCharging"},
    {"lat":3.1578,"lng":101.7120,"time":"2026-01-10T20:45","note":"Auto-synced","id":3,"updatedAt":1,"address":"Setapak, KL","accuracy":40,"battery":64,"batteryStatus":"NotCharging"},
    {"lat":3.1601,"lng":101.7210,"time":"2026-01-10T21:30","note":"Stopped here a while","id":4,"updatedAt":1,"address":"Wangsa Maju, KL","accuracy":30,"battery":55,"batteryStatus":"Charging"},
    {"lat":3.1601,"lng":101.7211,"time":"2026-01-11T00:30","note":"Auto-synced","id":5,"updatedAt":1,"address":"Wangsa Maju, KL","accuracy":28,"battery":90,"batteryStatus":"Charging"},
    {"lat":3.1599,"lng":101.7208,"time":"2026-01-11T02:30","note":"Auto-synced","id":6,"updatedAt":1,"address":"Wangsa Maju, KL","accuracy":33,"battery":99,"batteryStatus":"Charging"},
    {"lat":3.1490,"lng":101.6990,"time":"2026-01-11T09:15","note":"Auto-synced","id":7,"updatedAt":1,"address":"Titiwangsa, KL","accuracy":45,"battery":82,"batteryStatus":"NotCharging"},
]

def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run:\n  pip install playwright\n  playwright install chromium")
        return

    if LOC.exists(): shutil.copy(LOC, BACKUP)
    LOC.write_text(json.dumps(FAKE, indent=2), encoding="utf-8")
    httpd = serve()
    base = f"http://127.0.0.1:{PORT}"

    try:
        with sync_playwright() as p:
            b = p.chromium.launch()

            # Desktop trail map
            pg = b.new_page(viewport={"width":1280,"height":800})
            pg.goto(f"{base}/tracker.html"); pg.wait_for_selector(".leaflet-tile-loaded", timeout=15000); pg.wait_for_timeout(2500)
            pg.screenshot(path=str(DOCS/"trail-map.png")); print("✓ docs/trail-map.png")

            # Mobile trail + patterns
            m = b.new_page(viewport={"width":390,"height":844})
            m.goto(f"{base}/tracker.html"); m.wait_for_timeout(1500)
            m.click("#nav-trail"); m.wait_for_timeout(400)
            try: m.click("#patterns-toggle"); m.wait_for_timeout(500)
            except Exception: pass
            m.screenshot(path=str(DOCS/"mobile.png")); print("✓ docs/mobile.png")

            # Report
            r = b.new_page(viewport={"width":1100,"height":1400})
            r.goto(f"{base}/report.html"); r.wait_for_selector(".leaflet-tile-loaded", timeout=15000); r.wait_for_timeout(2500)
            r.screenshot(path=str(DOCS/"report.png"), full_page=True); print("✓ docs/report.png")

            b.close()
    finally:
        httpd.shutdown()
        if BACKUP.exists(): shutil.move(BACKUP, LOC)
        else: LOC.write_text("[]", encoding="utf-8")
        print("Restored locations.json")

if __name__ == "__main__":
    main()
