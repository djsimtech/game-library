"""
Builds the game library data from "Video Game Collection.xlsx".

For each row (Title, Platform) it looks the game up on IGDB, picks the
release date for that platform (North America first), downloads the box art,
and grabs a YouTube video ID. Results go to games.js, which index.html loads.

Usage (from this folder):
    pip install openpyxl
    python build_catalog.py            # look up new games only (cached ones are reused)
    python build_catalog.py --refresh  # look everything up again

Optional columns you can add to the sheet any time (header text must match):
    IGDB ID   - force a specific IGDB game when the automatic match is wrong
    Video     - a YouTube video ID or URL to use instead of IGDB's
    Start     - seconds into the video to start playing (e.g. 90)
    Released  - your own release date when IGDB's is wrong: 1989-11, 1989-11-15 or just 1989
    Cover     - your own box art: an image URL, or a file name in the covers folder (e.g. tetris-nes.jpg)
"""

import json
import os
import hashlib
import re
import sys
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl is missing. Run:  pip install openpyxl")

HERE = Path(__file__).resolve().parent
SHEET = HERE / "Video Game Collection.xlsx"
ENV = HERE / "igdb.env"
OUT_JS = HERE / "games.js"
COVERS = HERE / "covers"
REPORT = HERE / "match_report.txt"

# Sheet platform name -> IGDB platform name
PLATFORMS = {
    "NES": "Nintendo Entertainment System",
    "SNES": "Super Nintendo Entertainment System",
    "Game Boy": "Game Boy",
    "Game Boy Color": "Game Boy Color",
    "Game Boy Advance": "Game Boy Advance",
    "Nintendo 64": "Nintendo 64",
    "GameCube": "Nintendo GameCube",
    "Wii": "Wii",
    "Wii U": "Wii U",
    "Nintendo DS": "Nintendo DS",
    "Nintendo 3DS": "Nintendo 3DS",
    "Switch": "Nintendo Switch",
    "Switch 2": "Nintendo Switch 2",
    "PlayStation": "PlayStation",
    "PlayStation 2": "PlayStation 2",
    "PlayStation 3": "PlayStation 3",
    "PlayStation 4": "PlayStation 4",
    "PlayStation 5": "PlayStation 5",
    "PSP": "PlayStation Portable",
    "PS Vita": "PlayStation Vita",
    "Xbox": "Xbox",
    "Xbox 360": "Xbox 360",
    "Xbox One": "Xbox One",
    "Xbox Series X|S": "Xbox Series X|S",
    "Sega Genesis": "Sega Mega Drive/Genesis",
    "Sega Dreamcast": "Dreamcast",
}

GAME_FIELDS = (
    "name,slug,first_release_date,summary,cover.image_id,genres.name,"
    "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
    "release_dates.date,release_dates.platform,release_dates.region,release_dates.release_region,"
    "release_dates.category,release_dates.date_format,"
    "videos.video_id,videos.name,platforms"
)


# ---------- helpers ----------

def load_env():
    if not ENV.exists():
        sys.exit(f"Missing {ENV.name} with IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.")
    vals = {}
    for line in ENV.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    try:
        return vals["IGDB_CLIENT_ID"], vals["IGDB_CLIENT_SECRET"]
    except KeyError:
        sys.exit(f"{ENV.name} needs both IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.")


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    req.add_header("User-Agent", "game-library-builder")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(1 + attempt)
                continue
            body = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from None


def get_token(cid, secret):
    q = urllib.parse.urlencode({"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"})
    data = json.loads(http("https://id.twitch.tv/oauth2/token?" + q, data=b""))
    return data["access_token"]


class IGDB:
    def __init__(self, cid, token):
        self.h = {"Client-ID": cid, "Authorization": f"Bearer {token}", "Accept": "application/json"}

    def query(self, endpoint, body):
        time.sleep(0.27)  # IGDB allows 4 requests/second
        return json.loads(http(f"https://api.igdb.com/v4/{endpoint}", body.encode(), self.h))


def norm(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"\bthe\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def similarity(a, b):
    a, b = norm(a), norm(b)
    if a == b:
        return 1.0
    score = SequenceMatcher(None, a, b).ratio()
    # Sheet title contained in the IGDB title (e.g. "Adventure of Link" in "Zelda II: The Adventure of Link")
    if a and a in b:
        score = max(score, 0.85)
    return score


def youtube_id(v):
    if not v:
        return None
    v = str(v).strip()
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", v)
    if m:
        return m.group(1)
    return v if re.fullmatch(r"[A-Za-z0-9_-]{11}", v) else None


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------- picking data out of an IGDB game ----------

def platform_date(game, pid):
    """(timestamp, precision) for this platform: North America first, then earliest anywhere.
    precision is 'day', 'month' or 'year' - IGDB stores year-only dates as Dec 31."""
    dates = [d for d in game.get("release_dates", []) if d.get("platform") == pid and d.get("date")]
    na = [d for d in dates if d.get("region") == 2 or d.get("release_region") == 2]
    pick = min(na or dates, key=lambda d: d["date"]) if (na or dates) else None
    if not pick:
        ts = game.get("first_release_date")
        return ts, "day"
    fmt = pick.get("date_format", pick.get("category", 0))
    if isinstance(fmt, dict):
        fmt = fmt.get("id", 0)
    return pick["date"], {0: "day", 1: "month", 2: "year"}.get(fmt, "year")


def parse_released(v):
    """Turn a 'Released' cell (1989, 1989-11, 1989-11-15, or an Excel date) into (date, precision)."""
    if v is None or str(v).strip() == "":
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d"), "day"
    s = str(v).strip()
    if re.fullmatch(r"\d{4}(\.0)?", s):
        return f"{s[:4]}-12-31", "year"
    if re.fullmatch(r"\d{4}-\d{1,2}", s):
        y, m = s.split("-")
        return f"{y}-{int(m):02d}-01", "month"
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", s):
        y, m, d = s.split("-")
        return f"{y}-{int(m):02d}-{int(d):02d}", "day"
    print(f"  ! Couldn't read Released value {s!r} - use 1989, 1989-11 or 1989-11-15")
    return None


def pick_video(game):
    vids = game.get("videos") or []
    if not vids:
        return None
    for word in ("gameplay", "longplay", "playthrough"):
        for v in vids:
            if word in (v.get("name") or "").lower():
                return v["video_id"]
    return vids[0]["video_id"]


def companies(game, role):
    return [ic["company"]["name"] for ic in game.get("involved_companies", [])
            if ic.get(role) and ic.get("company")]


def download_cover(image_id):
    if not image_id:
        return None
    COVERS.mkdir(exist_ok=True)
    path = COVERS / f"{image_id}.jpg"
    if not path.exists():
        url = f"https://images.igdb.com/igdb/image/upload/t_cover_big_2x/{image_id}.jpg"
        path.write_bytes(http(url))
    return f"covers/{image_id}.jpg"


def custom_cover(v, game_id):
    """Box art from the 'Cover' column: an image URL (downloaded once) or a local file."""
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip()
    if s.lower().startswith(("http://", "https://")):
        ext = Path(urllib.parse.urlparse(s).path).suffix.lower()
        ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") else ".jpg"
        name = f"custom-{game_id}-{hashlib.sha1(s.encode()).hexdigest()[:8]}{ext}"
        path = COVERS / name
        if not path.exists():
            COVERS.mkdir(exist_ok=True)
            try:
                path.write_bytes(http(s))
            except Exception as e:
                print(f"  ! Couldn't download the cover for {game_id}: {e}")
                return None
        return f"covers/{name}"
    for candidate in (HERE / s, COVERS / s):
        if candidate.is_file():
            return candidate.relative_to(HERE).as_posix()
    print(f"  ! Cover file not found for {game_id}: {s} (put it in the covers folder)")
    return None


# ---------- main ----------

def read_sheet():
    wb = openpyxl.load_workbook(SHEET, data_only=True)
    ws = wb["Games"]
    headers = {str(c.value).strip().lower(): i for i, c in enumerate(ws[1]) if c.value}
    col = lambda name: headers.get(name.lower())
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        title = r[col("title")] if col("title") is not None else None
        if not title or not str(title).strip():
            continue
        get = lambda name: r[col(name)] if col(name) is not None and col(name) < len(r) else None
        rows.append({
            "title": str(title).strip(),
            "platform": str(get("platform") or "").strip(),
            "igdb_id": get("igdb id"),
            "video": get("video"),
            "start": get("start"),
            "released": get("released"),
            "cover": get("cover"),
        })
    return rows


def load_cache():
    if not OUT_JS.exists():
        return {}
    text = OUT_JS.read_text(encoding="utf-8")
    m = re.search(r"window\.GAMES\s*=\s*(\[.*\]);", text, re.S)
    if not m:
        return {}
    return {(g["sheetTitle"], g["platform"]): g for g in json.loads(m.group(1))}


def main():
    refresh = "--refresh" in sys.argv
    rows = read_sheet()
    cache = {} if refresh else load_cache()
    print(f"{len(rows)} games in the sheet.")

    cid, secret = load_env()
    api = None

    def igdb():
        nonlocal api
        if api is None:
            api = IGDB(cid, get_token(cid, secret))
        return api

    platform_ids = {}
    games, report = [], []

    for row in rows:
        key = (row["title"], row["platform"])
        cached = cache.get(key)
        same_override = cached and str(cached.get("igdbOverride") or "") == str(row["igdb_id"] or "")
        if cached and same_override:
            g = dict(cached)
        else:
            igdb_name = PLATFORMS.get(row["platform"], row["platform"])
            if igdb_name not in platform_ids:
                res = igdb().query("platforms", f'fields id,name; where name = "{igdb_name}";')
                platform_ids[igdb_name] = res[0]["id"] if res else None
            pid = platform_ids[igdb_name]

            if row["igdb_id"]:
                found = igdb().query("games", f"fields {GAME_FIELDS}; where id = {int(row['igdb_id'])};")
            else:
                q = row["title"].replace('"', "")
                where = f" where platforms = ({pid});" if pid else ""
                found = igdb().query("games", f'search "{q}"; fields {GAME_FIELDS};{where} limit 15;')
                if not found:  # retry without the platform filter
                    found = igdb().query("games", f'search "{q}"; fields {GAME_FIELDS}; limit 15;')

            if not found:
                report.append(f"NOT FOUND   {row['title']} ({row['platform']})")
                g = {"name": row["title"], "matched": None, "score": 0}
            else:
                best = max(found, key=lambda x: (similarity(row["title"], x["name"]),
                                                 pid in (x.get("platforms") or [])))
                score = 1.0 if row["igdb_id"] else similarity(row["title"], best["name"])
                ts, precision = platform_date(best, pid)
                g = {
                    "name": best["name"],
                    "igdbId": best["id"],
                    "igdbUrl": f"https://www.igdb.com/games/{best.get('slug', '')}",
                    "igdbRelease": time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else None,
                    "igdbPrecision": precision if ts else None,
                    "igdbCover": download_cover((best.get("cover") or {}).get("image_id")),
                    "summary": best.get("summary"),
                    "genres": [x["name"] for x in best.get("genres", [])],
                    "developer": companies(best, "developer"),
                    "publisher": companies(best, "publisher"),
                    "igdbVideo": pick_video(best),
                    "score": round(score, 2),
                }
            g["igdbOverride"] = row["igdb_id"] or None
            print(f"  {row['title']}  ->  {g['name']}")

        g["sheetTitle"], g["platform"] = row["title"], row["platform"]
        g["video"] = youtube_id(row["video"]) or g.get("igdbVideo")
        g["start"] = int(row["start"]) if row["start"] else 0
        own = parse_released(row["released"])
        g["release"], g["precision"] = own or (g.get("igdbRelease", g.get("release")), g.get("igdbPrecision", "day"))
        g["id"] = slugify(f"{row['platform']}-{g['name']}")
        g["cover"] = custom_cover(row["cover"], g["id"]) or g.get("igdbCover", g.get("cover"))
        clip = HERE / "clips" / f"{g['id']}.webm"
        g["clip"] = f"clips/{clip.name}" if clip.exists() else None
        games.append(g)

        if g.get("score", 0) < 0.8 and g.get("igdbId"):
            report.append(f"CHECK       {row['title']} ({row['platform']})  matched  {g['name']}  "
                          f"[IGDB ID {g['igdbId']}]")
        if not g.get("release") and g.get("igdbId"):
            report.append(f"NO DATE     {g['name']} ({row['platform']})")
        if not g["video"]:
            report.append(f"NO VIDEO    {g['name']} ({row['platform']})")

    OUT_JS.write_text(
        "// Generated by build_catalog.py - edit the spreadsheet, not this file.\n"
        f"window.GAMES = {json.dumps(games, indent=1, ensure_ascii=False)};\n",
        encoding="utf-8",
    )
    REPORT.write_text("\n".join(report) + "\n" if report else "Everything matched.\n", encoding="utf-8")

    print(f"\nWrote {OUT_JS.name} with {len(games)} games.")
    if report:
        print(f"{len(report)} item(s) to look at - see {REPORT.name}:")
        for line in report:
            print("  " + line)
        print("\nWrong match? Add an 'IGDB ID' column to the sheet with the right ID")
        print("(the number on the game's igdb.com page) and run this again.")


if __name__ == "__main__":
    main()
