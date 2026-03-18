#!/usr/bin/env python3
# v1 — Taegliches Briefing via GitHub Actions + Slack
# Liest alle Client-JSONs aus dem Repo, checkt Wetter + Feiertage,
# pusht kompaktes Briefing an Slack.

import json
import os
import sys
import glob
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

GITHUB_RAW = "https://raw.githubusercontent.com/mupdx/content-boards/main"
GITHUB_API = "https://api.github.com/repos/mupdx/content-boards/contents/clients"

# Bekannte Clients
CLIENTS = [
    {"id": "dolce-freddo-zwickau", "name": "Dolce Freddo Zwickau", "branch": "restaurant", "city": "Zwickau"},
    {"id": "eyestyle-zwickau", "name": "Eyestyle Zwickau", "branch": "optiker", "city": "Zwickau"},
]

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONATE = ["", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
          "Juli", "August", "September", "Oktober", "November", "Dezember"]

KANAL_ICONS = {
    "instagram_feed": "Feed ",
    "instagram_story": "Story",
    "facebook": "FB   ",
    "linkedin": "LI   ",
}

WETTER_CODES = {
    0: "sonnig", 1: "heiter", 2: "teilw. bewoelkt", 3: "bewoelkt",
    45: "Nebel", 48: "Nebel", 51: "Nieselregen", 53: "Nieselregen",
    55: "Nieselregen", 61: "Regen", 63: "Regen", 65: "starker Regen",
    71: "Schnee", 73: "Schnee", 75: "starker Schnee",
    80: "Regenschauer", 81: "Regenschauer", 82: "Starkregen",
    95: "Gewitter", 96: "Gewitter+Hagel", 99: "Gewitter+Hagel",
}

BRANCH_TRIGGERS = {
    "optiker": lambda temp, code: "Sonnenbrillen-Wetter!" if code <= 1 and temp >= 20 else None,
    "restaurant": lambda temp, code: "Terrassenwetter!" if temp >= 18 and code <= 2 else None,
}


def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BriefingBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def load_all_posts(client_id):
    posts = []

    # Direkte Client-Datei
    data = fetch_json(f"{GITHUB_RAW}/clients/{client_id}.json")
    if data and "posts" in data:
        posts.extend(data["posts"])

    # Alle Dateien im clients/ Ordner die zum Client gehoeren
    file_list = fetch_json(GITHUB_API)
    if file_list and isinstance(file_list, list):
        for f in file_list:
            name = f.get("name", "")
            if name.startswith(client_id) and name.endswith(".json") and name != f"{client_id}.json":
                data = fetch_json(f"{GITHUB_RAW}/clients/{name}")
                if data and "posts" in data:
                    posts.extend(data["posts"])

    # Lokale Archiv-Dateien (im Repo unter clients/)
    local_pattern = os.path.join("clients", f"{client_id}*.json")
    for filepath in glob.glob(local_pattern):
        try:
            with open(filepath) as fh:
                data = json.load(fh)
            if "posts" in data:
                posts.extend(data["posts"])
        except Exception:
            continue

    # Deduplizieren
    seen = {}
    for p in posts:
        key = f"{p.get('date')}|{p.get('channel')}|{p.get('time')}"
        if key not in seen or p.get("lastModified", "") >= seen[key].get("lastModified", ""):
            seen[key] = p
    return list(seen.values())


def get_weather(city="Zwickau"):
    coords = {"Zwickau": (50.72, 12.49)}
    lat, lon = coords.get(city, (50.72, 12.49))
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=Europe/Berlin"
    data = fetch_json(url)
    if data and "current_weather" in data:
        cw = data["current_weather"]
        temp = round(cw.get("temperature", 0))
        code = cw.get("weathercode", 0)
        return temp, WETTER_CODES.get(code, "unbekannt"), code
    return None, None, None


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
        date(jahr, 11, 23) - timedelta(days=(date(jahr, 11, 23).weekday() + 4) % 7): "Buss- und Bettag",
        date(jahr, 12, 25): "1. Weihnachtstag",
        date(jahr, 12, 26): "2. Weihnachtstag",
    }


def build_briefing(clients_data, target_date):
    wt = WOCHENTAGE[target_date.weekday()]
    tag = target_date.day
    monat = MONATE[target_date.month]

    temp, wetter_desc, wetter_code = get_weather()
    wetter_str = f"{temp} C {wetter_desc}" if temp is not None else "Wetter nicht verfuegbar"

    feiertage = feiertage_sachsen(target_date.year)
    heute_feiertag = feiertage.get(target_date)
    morgen_feiertag = feiertage.get(target_date + timedelta(days=1))

    lines = []
    lines.append(f":sunny: *Briefing {wt}, {tag}. {monat}*  |  :thermometer: Zwickau {wetter_str}")
    lines.append("")

    if heute_feiertag:
        lines.append(f":rotating_light: *FEIERTAG HEUTE: {heute_feiertag}*")
        lines.append("")
    if morgen_feiertag:
        lines.append(f":warning: Morgen Feiertag: _{morgen_feiertag}_")
        lines.append("")

    for client, all_posts in clients_data:
        name = client["name"]
        branch = client.get("branch", "")
        date_str = target_date.strftime("%Y-%m-%d")
        posts_today = [p for p in all_posts if p.get("date") == date_str]

        lines.append(f"━━━ *{name}* ━━━")

        if posts_today:
            for p in sorted(posts_today, key=lambda x: x.get("time", "")):
                channel = p.get("channel", "")
                if channel == "instagram_feed":
                    icon = ":camera:"
                elif channel == "instagram_story":
                    icon = ":iphone:"
                elif channel == "facebook":
                    icon = ":blue_book:"
                elif channel == "linkedin":
                    icon = ":briefcase:"
                else:
                    icon = ":memo:"

                kanal = KANAL_ICONS.get(channel, channel)
                zeit = p.get("time", "?")
                desc = p.get("image_description", "")
                if not desc:
                    caption = p.get("caption", p.get("caption_ig", ""))
                    if caption:
                        desc = caption[:45] + ("..." if len(caption) > 45 else "")
                if desc:
                    lines.append(f"  {icon} `{kanal}` *{zeit}*  _{desc}_")
                else:
                    lines.append(f"  {icon} `{kanal}` *{zeit}*")
        else:
            lines.append("  :zzz: _Nichts heute._")

        # Branchenspezifischer Trigger
        if temp is not None and branch in BRANCH_TRIGGERS:
            trigger = BRANCH_TRIGGERS[branch](temp, wetter_code or 0)
            if trigger:
                lines.append(f"  :bulb: {trigger}")

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
            if tage_rest <= 14:
                lines.append(f"  :warning: *Noch {tage_rest} Tage Content!* Letzter Post: {last.strftime('%d.%m.')}")
        else:
            lines.append("  :rotating_light: *KEIN Content geplant!*")

        lines.append("")

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
