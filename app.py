"""
Tennis Scores Demo App
======================
A minimal Flask app that scrapes live tennis scores from tennis.com
and serves them via a JSON API + a rich frontend.

STRUCTURE (maps to Django):
- This file      -> views.py + urls.py
- scrape_scores  -> services/scraper.py (or a management command)
- /api/scores    -> Django REST Framework ViewSet
- templates/     -> Django templates (no Django-specific tags used here)

Run:  python app.py
Then: open http://localhost:8000
"""

from flask import Flask, jsonify, render_template
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import copy
import threading

app = Flask(__name__)


# -------------------------------------------------------------------
# MATCH CACHE
# tennis.com/scores/ only shows *live* matches.  Once a match ends it
# vanishes from the page entirely.  We keep a per-session in-memory
# cache so recently completed results are still visible.
#
# In Django this would be a model (Match) or a Redis/memcached entry.
# -------------------------------------------------------------------

_match_cache = {}          # slug -> match dict
_cache_lock = threading.Lock()


# -------------------------------------------------------------------
# SCRAPER
# In a Django app, this would live in a separate module like
# scores/services/scraper.py or a management command.
# -------------------------------------------------------------------

SCORES_URL = "https://www.tennis.com/scores/"

# Pretend to be a normal browser so the site does not block us
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape_scores():
    """
    Fetch and parse tennis scores, merging two data sources:

    1. **Live matches** - scraped from tennis.com/scores/ HTML
    2. **Recently finished** - matches that were live but disappeared
       (kept in an in-memory cache, marked as RESULT)

    This mirrors a real Django pattern where you'd combine a live feed
    with a database of historical results.
    """
    live_matches = []
    try:
        response = requests.get(SCORES_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        live_matches = parse_scores_html(response.text)
    except requests.RequestException as e:
        print(f"Warning: Scraping failed ({e})")

    # Update the cache and build the combined list
    all_matches = update_cache(live_matches)

    # If there are no RESULT matches yet (server just started, or nothing
    # has finished), seed the cache with sample results so the demo always
    # showcases both statuses.
    has_results = any(m.get("status") == "RESULT" for m in all_matches)
    if not has_results:
        seed_sample_results()
        # Re-read cache without re-running promotion logic
        with _cache_lock:
            status_order = {"LIVE": 0, "RESULT": 1}
            all_matches = sorted(
                [_strip_internal(m) for m in _match_cache.values()],
                key=lambda m: (status_order.get(m.get("status"), 9), m.get("start_time", ""))
            )

    if all_matches:
        return all_matches

    print("Warning: No matches from any source - using sample data")
    return get_sample_data()


def seed_sample_results():
    """Inject sample RESULT matches into the cache for demo purposes."""
    with _cache_lock:
        for m in get_sample_data():
            if m.get("status") == "RESULT":
                slug = "sample-" + m["player1"]["name"].lower().replace(" ", "-")
                if slug not in _match_cache:
                    m["_slug"] = slug
                    m["_last_seen"] = datetime.now().isoformat()
                    _match_cache[slug] = m


# -------------------------------------------------------------------
# CACHE LOGIC
# -------------------------------------------------------------------

def update_cache(live_matches):
    """
    Merge live and cached-result matches.

    Logic:
    - Any match currently LIVE gets upserted into the cache.
    - Any cached match whose slug is NOT in the fresh live set and was
      previously LIVE gets promoted to RESULT (it just finished).
    - Returns combined list sorted: LIVE first, then RESULT.
    """
    with _cache_lock:
        live_slugs = set()

        # 1. Upsert live matches
        for m in live_matches:
            slug = m.get("_slug") or m.get("url", "")
            if not slug:
                continue
            live_slugs.add(slug)
            m["_slug"] = slug
            m["_last_seen"] = datetime.now().isoformat()
            _match_cache[slug] = m

        # 2. Promote disappeared live matches to RESULT
        for slug, cached in _match_cache.items():
            if slug not in live_slugs and cached.get("status") == "LIVE":
                cached["status"] = "RESULT"
                cached["_finished_at"] = datetime.now().isoformat()

        # 3. Build sorted output
        status_order = {"LIVE": 0, "RESULT": 1}
        all_matches = sorted(
            _match_cache.values(),
            key=lambda m: (status_order.get(m.get("status"), 9), m.get("start_time", ""))
        )

        # Strip internal keys before returning
        return [_strip_internal(m) for m in all_matches]


def _strip_internal(match):
    """Remove _-prefixed internal keys before sending to the client."""
    return {k: v for k, v in match.items() if not k.startswith("_")}


def parse_scores_html(html):
    """
    Parse tennis.com/scores/ HTML using the exact CSS class structure.

    Key classes discovered by inspecting the source:
      .tc-match              - match card container
      .tc-player__link       - has title='Full Name' and data-id
      .tc-player__flag-logo  - has alt='player country flag: XXX'
      .tc-player__seeding    - seed number e.g. '(1)'
      .tc-match__stats--set  - individual set score spans
      .tc-match[data-event]  - tournament name
      .tc-match[data-match-status] - 'live', 'ended', 'closed'
    """
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    seen_slugs = set()  # deduplicate (cards repeat in carousel)

    # Find all match card containers
    match_cards = soup.find_all("div", class_="tc-match")

    for card in match_cards:
        try:
            # --- Deduplicate (the page has a carousel with duplicates) ---
            slug = card.get("data-match-slug", "")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # --- Tournament name ---
            tournament = card.get("data-event", "Unknown Tournament")

            # --- Match status ---
            raw_status = card.get("data-match-status", "").lower()
            if raw_status == "live":
                status = "LIVE"
            elif raw_status in ("ended", "closed"):
                status = "RESULT"
            else:
                status = raw_status.upper() or "UNKNOWN"

            # --- Start time ---
            start_time = card.get("data-start-time", "")

            # --- Tournament slug (for building URLs) ---
            tournament_slug = card.get("data-tournament-slug", "")

            # --- Match URL ---
            match_url = f"https://www.tennis.com/tournaments/{tournament_slug}/{slug}/"

            # --- Round and event type ---
            round_el = card.find("span", class_="tc-round-name")
            round_name = round_el.get_text(strip=True) if round_el else ""
            event_el = card.find("span", class_="tc-event-title")
            event_name = event_el.get_text(strip=True) if event_el else ""

            # --- Players ---
            # Home player (player 1)
            home_div = card.find("div", class_=lambda c: c and "-home" in c)
            p1_name, p1_country, p1_seed, p1_flag_url = extract_player(home_div)

            # Away player (player 2)
            away_div = card.find("div", class_=lambda c: c and "-away" in c)
            p2_name, p2_country, p2_seed, p2_flag_url = extract_player(away_div)

            # --- Scores ---
            home_sets, home_game = extract_set_scores(home_div)
            away_sets, away_game = extract_set_scores(away_div)
            score_str = format_score(home_sets, away_sets, home_game, away_game, status)

            # --- Winner detection ---
            is_p1_winner = False
            is_p2_winner = False
            if home_div:
                home_classes = " ".join(home_div.get("class", []))
                is_p1_winner = "winner" in home_classes
            if away_div:
                away_classes = " ".join(away_div.get("class", []))
                is_p2_winner = "winner" in away_classes

            # Compute match intensity (how close/exciting the match is)
            intensity = compute_intensity(home_sets, away_sets, status)

            match_data = {
                "tournament": tournament,
                "round": round_name,
                "event": event_name,
                "status": status,
                "start_time": start_time,
                "player1": {
                    "name": p1_name,
                    "country": p1_country,
                    "seed": p1_seed,
                    "flag_url": p1_flag_url,
                    "is_winner": is_p1_winner,
                },
                "player2": {
                    "name": p2_name,
                    "country": p2_country,
                    "seed": p2_seed,
                    "flag_url": p2_flag_url,
                    "is_winner": is_p2_winner,
                },
                "score": score_str,
                "sets": {
                    "player1": [s["score"] for s in home_sets],
                    "player2": [s["score"] for s in away_sets],
                },
                "tiebreaks": {
                    "player1": [s.get("tiebreak", "") for s in home_sets],
                    "player2": [s.get("tiebreak", "") for s in away_sets],
                },
                "game_score": {
                    "player1": home_game,
                    "player2": away_game,
                },
                "intensity": intensity,
                "url": match_url,
                "_slug": slug,
            }
            matches.append(match_data)

        except Exception as e:
            print(f"  Skipping match card: {e}")
            continue

    return matches


def extract_player(player_div):
    """Extract player name, country, seed, and flag URL from a player div."""
    if not player_div:
        return "TBD", "", None, ""

    # Full name from <a class="tc-player__link" title="Full Name">
    link = player_div.find("a", class_="tc-player__link")
    name = link.get("title", "Unknown") if link else "Unknown"

    # Country from flag image alt text: alt="player country flag: GBR"
    flag_img = player_div.find("img", class_="tc-player__flag-logo")
    country = ""
    flag_url = ""
    if flag_img:
        alt = flag_img.get("alt", "")
        if ":" in alt:
            country = alt.split(":")[-1].strip()
        flag_url = flag_img.get("src", "")

    # Seed from <small class="tc-player__seeding">(1)</small>
    seed_el = player_div.find("small", class_="tc-player__seeding")
    seed = None
    if seed_el:
        seed_text = seed_el.get_text(strip=True).strip("()")
        try:
            seed = int(seed_text)
        except ValueError:
            seed = None

    return name, country, seed, flag_url


def extract_set_scores(player_div):
    """
    Extract set scores and current game score for a player.

    The HTML uses modifier classes on each score span:
      - no modifier / '-win' / '-live'  -> set score
      - '-game'                         -> current game score (15, 30, 40, AD)

    Tiebreak scores appear as <sup> inside the span: '6 <sup>3</sup>'
    means the player won 6 games in a tiebreak that finished 7-3.

    Returns (sets, game_score) where:
      - sets is a list of dicts: [{"score": "6", "tiebreak": "3"}, ...]
      - game_score is a string like "30" or "" if none
    """
    if not player_div:
        return [], ""

    sets = []
    game_score = ""

    score_spans = player_div.find_all(
        "span", class_=lambda c: c and "tc-match__stats--set" in c
    )

    for span in score_spans:
        classes = " ".join(span.get("class", []))

        # Current game score (e.g. 15, 30, 40, AD)
        if "-game" in classes:
            text = span.get_text(strip=True)
            if text and text != "-":
                game_score = text
            continue

        # Set score — make a copy so we don't mutate the soup
        sc = copy.copy(span)
        sup = sc.find("sup")
        tiebreak = ""
        if sup:
            tiebreak = sup.get_text(strip=True)
            sup.decompose()

        main = sc.get_text(strip=True)
        if main and main != "-":
            sets.append({"score": main, "tiebreak": tiebreak})

    return sets, game_score


def format_score(home_sets, away_sets, home_game, away_game, status):
    """
    Build a readable score string from structured set/game data.

    home_sets = [{"score":"6","tiebreak":""},{"score":"4","tiebreak":""}]
    away_sets = [{"score":"3","tiebreak":""},{"score":"5","tiebreak":""}]
    -> '6-3  4-5'

    Tiebreak example: {"score":"7","tiebreak":""} vs {"score":"6","tiebreak":"5"}
    -> '7-6(5)'  (the loser's tiebreak points in parentheses)

    Appends current game score if present: '6-3  4-5  (30-15)'
    """
    if not home_sets and not away_sets:
        return "Score unavailable"

    pairs = []
    max_sets = max(len(home_sets), len(away_sets))
    for i in range(max_sets):
        h = home_sets[i]["score"] if i < len(home_sets) else "?"
        a = away_sets[i]["score"] if i < len(away_sets) else "?"
        # Append tiebreak as superscript notation
        h_tb = home_sets[i].get("tiebreak", "") if i < len(home_sets) else ""
        a_tb = away_sets[i].get("tiebreak", "") if i < len(away_sets) else ""
        h_str = f"{h}({h_tb})" if h_tb else h
        a_str = f"{a}({a_tb})" if a_tb else a
        pairs.append(f"{h_str}-{a_str}")

    result = "  ".join(pairs)

    # Append current game score
    if home_game or away_game:
        result += f"  ({home_game}-{away_game})"

    return result


def compute_intensity(home_sets, away_sets, status):
    """
    Rate match excitement from 1-5 based on score closeness.
    5 = epic match, 1 = blowout. Fun 'novel' metric for the demo.

    home_sets/away_sets are lists of {"score": "6", "tiebreak": "3"} dicts.
    """
    if not home_sets or not away_sets:
        return 3  # neutral for unknown

    num_sets = max(len(home_sets), len(away_sets))
    close_sets = 0

    for i in range(min(len(home_sets), len(away_sets))):
        try:
            h = int(home_sets[i]["score"])
            a = int(away_sets[i]["score"])
            if abs(h - a) <= 2:
                close_sets += 1
            # Tiebreaks always count as close
            if home_sets[i].get("tiebreak") or away_sets[i].get("tiebreak"):
                close_sets += 1
        except (ValueError, KeyError):
            pass

    intensity = min(num_sets, 3) + min(close_sets, 2)
    return min(intensity, 5)


def get_sample_data():
    """Rich sample data for when scraping fails."""
    return [
        {
            "tournament": "BNP Paribas Open", "round": "3rd Round", "event": "Men's Singles",
            "status": "LIVE", "start_time": "2026-03-02T19:00:00+00:00",
            "player1": {"name": "Carlos Alcaraz", "country": "ESP", "seed": 1, "flag_url": "", "is_winner": False},
            "player2": {"name": "Alex de Minaur", "country": "AUS", "seed": 8, "flag_url": "", "is_winner": False},
            "score": "6-3  4-5  (30-15)", "sets": {"player1": ["6", "4"], "player2": ["3", "5"]},
            "tiebreaks": {"player1": ["", ""], "player2": ["", ""]},
            "game_score": {"player1": "30", "player2": "15"},
            "intensity": 4, "url": "https://www.tennis.com/tournaments/sr-tournament-2737-indian-wells-usa/",
        },
        {
            "tournament": "BNP Paribas Open", "round": "3rd Round", "event": "Women's Singles",
            "status": "LIVE", "start_time": "2026-03-02T18:30:00+00:00",
            "player1": {"name": "Iga Swiatek", "country": "POL", "seed": 2, "flag_url": "", "is_winner": False},
            "player2": {"name": "Elina Svitolina", "country": "UKR", "seed": 15, "flag_url": "", "is_winner": False},
            "score": "3-6  6-4  2-1  (40-30)", "sets": {"player1": ["3", "6", "2"], "player2": ["6", "4", "1"]},
            "tiebreaks": {"player1": ["", "", ""], "player2": ["", "", ""]},
            "game_score": {"player1": "40", "player2": "30"},
            "intensity": 5, "url": "https://www.tennis.com/tournaments/sr-tournament-2737-indian-wells-usa/",
        },
        {
            "tournament": "BNP Paribas Open", "round": "3rd Round", "event": "Men's Singles",
            "status": "RESULT", "start_time": "2026-03-02T17:00:00+00:00",
            "player1": {"name": "Jannik Sinner", "country": "ITA", "seed": 3, "flag_url": "", "is_winner": True},
            "player2": {"name": "Stefanos Tsitsipas", "country": "GRE", "seed": 9, "flag_url": "", "is_winner": False},
            "score": "6-4  7-6(5)", "sets": {"player1": ["6", "7"], "player2": ["4", "6"]},
            "tiebreaks": {"player1": ["", ""], "player2": ["", "5"]},
            "game_score": {"player1": "", "player2": ""},
            "intensity": 4, "url": "https://www.tennis.com/tournaments/sr-tournament-2737-indian-wells-usa/",
        },
        {
            "tournament": "BNP Paribas Open", "round": "3rd Round", "event": "Women's Singles",
            "status": "RESULT", "start_time": "2026-03-02T16:00:00+00:00",
            "player1": {"name": "Aryna Sabalenka", "country": "BLR", "seed": 1, "flag_url": "", "is_winner": True},
            "player2": {"name": "Jessica Pegula", "country": "USA", "seed": 6, "flag_url": "", "is_winner": False},
            "score": "6-2  3-6  7-5", "sets": {"player1": ["6", "3", "7"], "player2": ["2", "6", "5"]},
            "tiebreaks": {"player1": ["", "", ""], "player2": ["", "", ""]},
            "game_score": {"player1": "", "player2": ""},
            "intensity": 5, "url": "https://www.tennis.com/tournaments/sr-tournament-2737-indian-wells-usa/",
        },
        {
            "tournament": "BNP Paribas Open", "round": "Qual", "event": "Men's Singles",
            "status": "RESULT", "start_time": "2026-03-02T15:00:00+00:00",
            "player1": {"name": "Tommy Paul", "country": "USA", "seed": 12, "flag_url": "", "is_winner": True},
            "player2": {"name": "Ben Shelton", "country": "USA", "seed": 14, "flag_url": "", "is_winner": False},
            "score": "7-6(3)  6-3", "sets": {"player1": ["7", "6"], "player2": ["6", "3"]},
            "tiebreaks": {"player1": ["", ""], "player2": ["3", ""]},
            "game_score": {"player1": "", "player2": ""},
            "intensity": 4, "url": "https://www.tennis.com/tournaments/sr-tournament-2737-indian-wells-usa/",
        },
        {
            "tournament": "BNP Paribas Open", "round": "Qual", "event": "Women's Singles",
            "status": "RESULT", "start_time": "2026-03-02T14:30:00+00:00",
            "player1": {"name": "Coco Gauff", "country": "USA", "seed": 4, "flag_url": "", "is_winner": True},
            "player2": {"name": "Danielle Collins", "country": "USA", "seed": None, "flag_url": "", "is_winner": False},
            "score": "4-6  6-4  6-2", "sets": {"player1": ["4", "6", "6"], "player2": ["6", "4", "2"]},
            "tiebreaks": {"player1": ["", "", ""], "player2": ["", "", ""]},
            "game_score": {"player1": "", "player2": ""},
            "intensity": 5, "url": "https://www.tennis.com/tournaments/sr-tournament-2737-indian-wells-usa/",
        },
        {
            "tournament": "ATP Challenger Brasilia", "round": "SF", "event": "Men's Singles",
            "status": "RESULT", "start_time": "2026-03-02T13:00:00+00:00",
            "player1": {"name": "Francisco Cerundolo", "country": "ARG", "seed": 2, "flag_url": "", "is_winner": True},
            "player2": {"name": "Luca Nardi", "country": "ITA", "seed": 5, "flag_url": "", "is_winner": False},
            "score": "6-1  6-4", "sets": {"player1": ["6", "6"], "player2": ["1", "4"]},
            "tiebreaks": {"player1": ["", ""], "player2": ["", ""]},
            "game_score": {"player1": "", "player2": ""},
            "intensity": 1, "url": "https://www.tennis.com/tournaments/sr-tournament-35528-atp-challenger-brasilia-brazil/",
        },
        {
            "tournament": "WTA 125K Antalya", "round": "F", "event": "Women's Singles",
            "status": "RESULT", "start_time": "2026-03-02T12:00:00+00:00",
            "player1": {"name": "Marta Kostyuk", "country": "UKR", "seed": 1, "flag_url": "", "is_winner": True},
            "player2": {"name": "Anastasia Potapova", "country": "RUS", "seed": 3, "flag_url": "", "is_winner": False},
            "score": "6-3  6-1", "sets": {"player1": ["6", "6"], "player2": ["3", "1"]},
            "tiebreaks": {"player1": ["", ""], "player2": ["", ""]},
            "game_score": {"player1": "", "player2": ""},
            "intensity": 1, "url": "https://www.tennis.com/tournaments/sr-tournament-45597-wta-125k-antalya-2-turkey/",
        },
    ]


# -------------------------------------------------------------------
# ROUTES (Django equivalent: urls.py + views.py)
# -------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main page."""
    return render_template("index.html")


@app.route("/api/scores")
def api_scores():
    """
    JSON API for scores with rich data.

    Django equivalent (with DRF):
        class MatchViewSet(viewsets.ViewSet):
            def list(self, request):
                data = scrape_scores()
                return Response(data)
    """
    matches = scrape_scores()
    status_counts = {}
    for m in matches:
        s = m.get("status", "UNKNOWN")
        status_counts[s] = status_counts.get(s, 0) + 1
    return jsonify({
        "matches": matches,
        "count": len(matches),
        "status_counts": status_counts,
        "source": SCORES_URL,
        "fetched_at": datetime.now().isoformat(),
    })


# -------------------------------------------------------------------
# RUN THE SERVER  (Django equivalent: python manage.py runserver)
# -------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  Tennis Scores Demo")
    print("   http://localhost:8000      <- Web UI")
    print("   http://localhost:8000/api/scores  <- JSON API\n")
    app.run(debug=True, port=8000)
