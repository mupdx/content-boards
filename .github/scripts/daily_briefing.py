#!/usr/bin/env python3
# v2 — Taegliches Briefing via GitHub Actions + Slack
# Liest Archiv-JSONs aus clients/archiv/, checkt Wetter + Feiertage,
# pusht kompaktes Briefing an Slack mit Custom Emojis.
# Laeuft auf GitHub Actions — braucht KEINEN lokalen Rechner.

import json
import os
import sys
import glob
import urllib.request
from datetime import datetime, date, timedelta

CLIENTS = [
    {"id": "dolce-freddo-zwickau", "name": "Dolce Freddo Zwickau"},
    {"id": "eyestyle-zwickau", "name": "Eyestyle Zwickau"},
    {"id": "calice-zwickau", "name": "Calice Zwickau"},
]

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONATE = ["", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
          "Juli", "August", "September", "Oktober", "November", "Dezember"]

KANAL_ICONS = {
    "instagram_feed": ":instagram:",
    "instagram_story": ":story:",
    "facebook": ":facebook:",
    "linkedin": ":linkedin:",
}

WETTER_CODES = {
    0: ("sonnig", ":sunny:"), 1: ("heiter", ":sun_behind_cloud:"),
    2: ("teilw. bewoelkt", ":partly_sunny:"), 3: ("bewoelkt", ":cloud:"),
    45: ("Nebel", ":fog:"), 48: ("Nebel", ":fog:"),
    51: ("Nieselregen", ":cloud_rain:"), 53: ("Nieselregen", ":cloud_rain:"),
    55: ("Nieselregen", ":cloud_rain:"), 61: ("Regen", ":rain_cloud:"),
    63: ("Regen", ":rain_cloud:"), 65: ("starker Regen", ":rain_cloud:"),
    71: ("Schnee", ":snowflake:"), 73: ("Schnee", ":snowflake:"),
    75: ("starker Schnee", ":snowflake:"),
    80: ("Regenschauer", ":rain_cloud:"), 81: ("Regenschauer", ":rain_cloud:"),
    82: ("Starkregen", ":rain_cloud:"),
    95: ("Gewitter", ":zap:"), 96: ("Gewitter+Hagel", ":zap:"),
    99: ("Gewitter+Hagel", ":zap:"),
}


def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BriefingBot/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def load_all_posts(client_id):
    posts = []

    # Board-JSON (aktives Board)
    board_path = os.path.join("clients", f"{client_id}.json")
    if os.path.exists(board_path):
        try:
            with open(board_path) as f:
                data = json.load(f)
            if data.get("posts"):
                posts.extend(data["posts"])
        except Exception:
            pass

    # Archiv-Dateien
    archiv_pattern = os.path.join("clients", "archiv", f"{client_id}*.json")
    for filepath in sorted(glob.glob(archiv_pattern)):
        try:
            with open(filepath) as f:
                data = json.load(f)
            if "posts" in data:
                posts.extend(data["posts"])
        except Exception:
            continue

    # Deduplizieren
    seen = {}
    for p in posts:
        key = f"{p.get('date')}|{p.get('channel')}|{p.get('time')}"
        seen[key] = p
    return list(seen.values())


def get_weather():
    url = "https://api.open-meteo.com/v1/forecast?latitude=50.72&longitude=12.49&current_weather=true&timezone=Europe/Berlin"
    data = fetch_json(url)
    if data and "current_weather" in data:
        cw = data["current_weather"]
        temp = round(cw.get("temperature", 0))
        code = cw.get("weathercode", 0)
        desc, emoji = WETTER_CODES.get(code, ("unbekannt", ":question:"))
        return temp, desc, emoji
    return None, None, ":question:"


def berechne_ostern(jahr):
    a = jahr % 19
    b = jahr // 100
    c = jahr % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = ((h + l - 7 * m + 114) % 31) + 1
    return date(jahr, monat, tag)


def feiertage_sachsen(jahr):
    ostern = berechne_ostern(jahr)
    return {
        date(jahr, 1, 1): "Neujahr",
        ostern - timedelta(days=2): "Karfreitag",
        ostern: "Ostersonntag",
        ostern + timedelta(days=1): "Ostermontag",
        date(jahr, 5, 1): "Tag der Arbeit",
        ostern + timedelta(days=39): "Christi Himmelfahrt",
        ostern + timedelta(days=49): "Pfingstsonntag",
        ostern + timedelta(days=50): "Pfingstmontag",
        date(jahr, 10, 3): "Tag der Dt. Einheit",
        date(jahr, 10, 31): "Reformationstag",
        date(jahr, 12, 25): "1. Weihnachtstag",
        date(jahr, 12, 26): "2. Weihnachtstag",
    }


def build_briefing(clients_data, target_date):
    wt = WOCHENTAGE[target_date.weekday()]
    tag = target_date.day
    monat = MONATE[target_date.month]

    temp, wetter_desc, wetter_emoji = get_weather()
    wetter_str = f"{temp}°C {wetter_desc}" if temp is not None else "Wetter nicht verfuegbar"

    feiertage = feiertage_sachsen(target_date.year)
    heute_feiertag = feiertage.get(target_date)

    lines = []
    lines.append(f"*Briefing {tag}. {monat}*")
    lines.append(f"Zwickau {wetter_str} {wetter_emoji}")
    lines.append("")

    if heute_feiertag:
        lines.append(f":rotating_light: *FEIERTAG: {heute_feiertag}*")
        lines.append("")

    for client, all_posts in clients_data:
        name = client["name"]
        date_str = target_date.strftime("%Y-%m-%d")
        posts_today = [p for p in all_posts if p.get("date") == date_str]

        lines.append(f":client: *{name}*")
        lines.append("")

        if posts_today:
            for p in sorted(posts_today, key=lambda x: x.get("time", "")):
                channel = p.get("channel", "")
                icon = KANAL_ICONS.get(channel, ":memo:")
                zeit = p.get("time", "?")

                desc = p.get("image_description", "")
                desc_str = f" · [{desc}]" if desc else ""

                lines.append(f"{icon}  *{zeit}*{desc_str}")

                if channel != "instagram_story":
                    caption = p.get("caption", p.get("caption_ig", ""))
                    if caption:
                        if len(caption) > 80:
                            caption = caption[:77] + "..."
                        lines.append(f"_{caption}_")

                lines.append("")
        else:
            lines.append("Keine Posts heute.")
            lines.append("")

        # 14-Tage-Warnung
        future_dates = []
        for p in all_posts:
            try:
                d = datetime.strptime(p["date"], "%Y-%m-%d").date()
                if d >= target_date:
                    future_dates.append(d)
            except (ValueError, KeyError):
                continue

        if future_dates:
            last = max(future_dates)
            tage_rest = (last - target_date).days
            if tage_rest <= 7:
                lines.append(f":rotating_light: *DRINGEND: Nur noch {tage_rest} Tage Content! Letzter Post: {last.strftime('%d.%m.')}*")
                lines.append("")
            elif tage_rest <= 14:
                lines.append(f":warning: *Noch {tage_rest} Tage Content bis {last.strftime('%d.%m.')}*")
                lines.append("")
        else:
            lines.append(":rotating_light: *KEIN Content geplant!*")
            lines.append("")

    lines.append("")
    lines.append(":arrow: :arrow: :arrow: :arrow: :arrow: :arrow: :arrow: :arrow: :arrow:")

    return "\n".join(lines).strip()


def send_slack(message, webhook_url):
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Slack-Fehler: {e}")
        return False


def main():
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        print("FEHLER: SLACK_WEBHOOK_URL nicht gesetzt!")
        sys.exit(1)

    target_date = date.today()
    print(f"Briefing fuer {target_date}")

    clients_data = []
    for client in CLIENTS:
        all_posts = load_all_posts(client["id"])
        print(f"  {client['name']}: {len(all_posts)} Posts geladen")
        clients_data.append((client, all_posts))

    briefing = build_briefing(clients_data, target_date)
    print(f"\n{briefing}\n")

    if send_slack(briefing, webhook):
        print("Briefing an Slack gesendet!")
    else:
        print("FEHLER beim Senden!")
        sys.exit(1)


if __name__ == "__main__":
    main()
