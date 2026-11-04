# Danny's Game Library

A catalog of my physical video game collection, sorted by release date. Click a game to watch gameplay.

## Updating the catalog

1. Add games to `Video Game Collection.xlsx` (Title + Platform) and save.
2. Run the builder from this folder:

   ```
   pip install openpyxl        # first time only
   python build_catalog.py
   ```

   It looks up each new game on IGDB, downloads box art into `covers/`, and writes `games.js`.
   Games already in `games.js` are reused; `python build_catalog.py --refresh` looks everything up again.
3. Check `match_report.txt` for anything flagged.
4. Preview it with a local web server (YouTube videos refuse to play when `index.html` is opened directly as a file):

   ```
   python -m http.server 8000
   ```

   Then browse to http://localhost:8000. When it looks right, commit and push.

## Fixing things from the spreadsheet

Add any of these columns to the Games sheet when you need them (header text must match):

| Column    | What it does |
|-----------|--------------|
| `IGDB ID` | Forces the right game when the automatic match is wrong. Use the number shown as "IGDB ID" on the game's igdb.com page. |
| `Video`   | A YouTube URL or video ID to use instead of IGDB's pick. |
| `Start`   | Seconds into the video to start playing. |
| `Released` | Your own release date when IGDB's is wrong: `1989`, `1989-11` or `1989-11-15`. |
| `Cover`   | Your own box art: an image URL, or a file name you've put in the `covers` folder (e.g. `tetris-nes.jpg`). |

## Hover clips (optional)

Drop a short muted clip at `clips/<game-id>.webm` (the id is in `games.js`, e.g. `nes-metroid`) and re-run the builder. That card then plays the clip on hover. Keep clips around 5–10 seconds at 480p.

## Credentials

`igdb.env` holds the Twitch/IGDB client ID and secret. It's in `.gitignore` and must never be committed.
