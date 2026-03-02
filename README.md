# Tennis Scores Demo

A minimal web app that scrapes live tennis scores from
[tennis.com/scores](https://www.tennis.com/scores/) and displays them
on a dark dashboard with grouping, sorting, intensity ratings, and
set-by-set score grids.

**Built to mirror Django patterns** — but runs standalone with Flask
so you can demo it instantly.

---

## Quick Start

```bash
# 1. Create a virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies (just 3 packages)
pip install -r requirements.txt

# 3. Run the app
python app.py
```

Then open **http://localhost:8000** in your browser.

---

## What You'll See

A dark-themed dashboard showing every match in a **five-column grid row**:

| Column | What it shows |
|--------|---------------|
| Status badge | **LIVE** (pulsing red) or **RESULT** (green) |
| Players | Flag emoji, full name, seed number `[3]` — winner in bold |
| Score | Set-by-set mini grid with tiebreak superscripts (e.g. 6 with a tiny 3) |
| Intensity | 1-5 coloured dots rating how close the match is |
| Meta | Tournament name and round |

You can **group** matches (by country, tournament, status, intensity, or
event type), **filter** by status, and **sort** by intensity, seed, name,
or tournament.

---

## Project Structure

```
tennis-scores/
├── app.py              <- Server + scraper + cache  (Django: views.py + services/)
├── templates/
│   └── index.html      <- Dashboard page  (no framework-specific template tags)
├── static/
│   ├── style.css       <- All styling — heavily commented, 14 numbered sections
│   └── app.js          <- Client-side fetch, group, sort, filter, render
├── requirements.txt    <- Python dependencies  (flask, requests, beautifulsoup4, gunicorn)
├── Procfile            <- For Render / Railway / Heroku deploys
├── render.yaml         <- Render Blueprint — auto-configures the service on import
├── vercel.json         <- Vercel config (works but no in-memory cache)
├── .gitignore          <- Excludes venv/, __pycache__/, .env, IDE files, etc.
└── README.md           <- You are here
```

---

## How It Maps to Django

| This Demo (Flask) | Django Equivalent | What it does |
|--------------------|-------------------|--------------|
| `app.py` routes | `urls.py` + `views.py` | Maps URLs to handler functions |
| `scrape_scores()` | `scores/services.py` or management command | Business logic (fetching + parsing) |
| `/api/scores` endpoint | DRF ViewSet (see below) | Returns JSON to the frontend |
| `jsonify({...})` | DRF Serializer (see below) | Converts Python dicts to JSON |
| In-memory `_match_cache` | Django ORM `Match` model + database | Stores match data persistently |
| `templates/index.html` | Django template | The HTML page |
| `static/` folder | `STATICFILES_DIRS` | CSS, JS, images |
| `python app.py` | `python manage.py runserver` | Start the dev server |

### Steps to convert this to Django

1. `django-admin startproject tennis_project`
2. `python manage.py startapp scores`
3. Move `scrape_scores()` into `scores/services.py`
4. Create a `Match` model in `scores/models.py`
5. Create a DRF serializer + viewset for the API
6. Move the template into `scores/templates/scores/`

---

## Key Concepts Explained

### What is a DRF Serializer?

**DRF** = Django REST Framework — a popular add-on library that makes
it easy to build JSON APIs in Django.

A **serializer** is a class that converts between two worlds:

| Direction | What happens |
|-----------|-------------|
| **Serialization** (Python to JSON) | Takes a Django model instance (or a dictionary) and turns it into a JSON-friendly format that can be sent to a browser or mobile app. |
| **Deserialization** (JSON to Python) | Takes incoming JSON from a POST/PUT request, validates it, and converts it into a Python object you can save to the database. |

Think of it as a **translator + bouncer** — it translates data formats
AND enforces rules (required fields, max lengths, valid choices, etc.).

#### Concrete example for this project

In our Flask demo, the `/api/scores` endpoint just does:

```python
return jsonify({"matches": matches, "count": len(matches)})
```

In Django with DRF, you would instead define a serializer class:

```python
# scores/serializers.py
from rest_framework import serializers

class PlayerSerializer(serializers.Serializer):
    name      = serializers.CharField()
    country   = serializers.CharField(allow_blank=True)
    seed      = serializers.IntegerField(allow_null=True)
    flag_url  = serializers.URLField(allow_blank=True)
    is_winner = serializers.BooleanField()

class MatchSerializer(serializers.Serializer):
    tournament = serializers.CharField()
    round      = serializers.CharField()
    event      = serializers.CharField()
    status     = serializers.ChoiceField(choices=["LIVE", "RESULT"])
    start_time = serializers.DateTimeField()
    player1    = PlayerSerializer()          # nested serializer
    player2    = PlayerSerializer()
    score      = serializers.CharField()
    intensity  = serializers.IntegerField(min_value=1, max_value=5)
    url        = serializers.URLField()
```

Then in your view:

```python
# scores/views.py
from rest_framework.response import Response
from rest_framework.views import APIView

class ScoresView(APIView):
    def get(self, request):
        matches = scrape_scores()                          # same function as our demo
        serializer = MatchSerializer(matches, many=True)   # many=True = list of items
        return Response({"matches": serializer.data})
```

**Why bother?** In a small demo like ours, `jsonify()` is simpler. But
serializers become essential when you need:

- **Validation** — reject bad input (e.g. intensity of 99)
- **Nested objects** — `PlayerSerializer` inside `MatchSerializer`
  (handles the nesting automatically)
- **Database integration** — `ModelSerializer` can create/update Django
  model instances directly from JSON
- **Browsable API** — DRF gives you a free HTML interface at each
  endpoint for testing

---

### What is a ViewSet?

A **ViewSet** groups related API operations into a single class. Instead
of writing separate functions for "list all matches", "get one match",
"create a match", "delete a match", DRF lets you write:

```python
from rest_framework import viewsets

class MatchViewSet(viewsets.ViewSet):
    def list(self, request):          # GET /api/matches/
        ...
    def retrieve(self, request, pk):  # GET /api/matches/42/
        ...
```

DRF auto-generates the URL routes for you. Our demo only needs `list`
(get all matches), but a full app would use `retrieve`, `create`,
`update`, and `destroy` too.

---

### What is BeautifulSoup?

A Python library for **parsing HTML**. When you fetch a web page with
`requests.get()`, you get back a giant string of HTML. BeautifulSoup
turns that string into a tree structure you can search:

```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(html_string, "html.parser")

# Find all <div> elements with a specific class
cards = soup.find_all("div", class_="tc-match")

# Get an attribute value from an element
name = card.find("a", class_="tc-player__link").get("title")
```

It is called "Beautiful Soup" after a line in _Alice's Adventures in
Wonderland_. The name refers to the messy ("tag soup") HTML that real
websites produce — the library handles it gracefully.

---

### What is a Virtual Environment (venv)?

A **venv** is an isolated folder that contains its own copy of Python
and installed packages, separate from your system Python. This prevents
version conflicts between projects.

```bash
python3 -m venv venv      # creates a folder called "venv"
source venv/bin/activate   # activates it (your prompt changes)
pip install flask          # installed ONLY inside this venv
deactivate                 # go back to system Python
```

When a venv is active, `python` and `pip` point to the copies inside the
`venv/` folder. Deleting the folder removes everything cleanly.

---

### What is Gunicorn?

**Gunicorn** (Green Unicorn) is a production-grade web server for Python
apps. Flask's built-in server (`app.run()`) is fine for development but
handles only one request at a time and is not hardened for the internet.

```bash
# Development (what we use)
python app.py

# Production (what you would deploy with)
gunicorn app:app --bind 0.0.0.0:8000 --workers 4
```

`app:app` means "in the file `app.py`, use the variable called `app`".
The `--workers 4` flag runs four parallel processes to handle traffic.

---

### What is a Procfile?

A one-line file that tells cloud platforms (Render, Railway, Heroku) how
to start your app:

```
web: gunicorn app:app
```

`web:` means "this is a web process". The platform reads this and runs
the command after the colon.

---

### What does jsonify() do?

Flask's `jsonify()` takes a Python dictionary and:

1. Converts it to a JSON string (like `json.dumps()`)
2. Sets the HTTP response header `Content-Type: application/json`
3. Returns a proper Flask `Response` object

Without it, the browser would not know the response is JSON and might
try to display it as plain text.

---

### What is CSS Grid vs Flexbox?

Both are CSS layout systems. This project uses both:

| System | Best for | Used where |
|--------|----------|------------|
| **Flexbox** | One-dimensional layouts (a row OR a column) | Controls bar, player lines, intensity dots, summary stats |
| **Grid** | Two-dimensional layouts (rows AND columns at once) | Match row (5 aligned columns across all matches) |

The match row uses Grid because we need the status badge, names, scores,
intensity, and meta columns to **line up across every row** — even when
"Iga Swiatek" is much shorter than "Francisco Cerundolo". Flexbox cannot
enforce cross-row alignment like that.

---

### What is font-variant-numeric: tabular-nums?

Normally, digits in proportional fonts have different widths (1 is
narrower than 8). `tabular-nums` forces all digits to the same width, so
score columns align perfectly:

```
6  7  6       <- without tabular-nums, columns might drift
6  7  6       <- with tabular-nums, columns always align
```

This matters in our set-score boxes where "1" and "7" must take equal
space.

---

### What are the hex colour codes in the CSS?

The stylesheet uses hex colour codes like `#ef4444`. Here is how to read
them:

| Code | Colour | Where used |
|------|--------|------------|
| `#0f1114` | Near-black (blue tint) | Page background |
| `#1a1d23` | Dark grey | Card surfaces |
| `#ef4444` | Red | LIVE badge, current score |
| `#10b981` | Green | RESULT badge |
| `#f59e0b` | Amber | Seed badges, mid-intensity |
| `#2563eb` | Blue | Buttons, links |

The `1a` suffix you will see on some colours (like `#dc26261a`) means
**10% opacity** — it creates a faint tinted background without being
heavy.

---

## How the Scraper Works

1. Fetches the HTML from `https://www.tennis.com/scores/` using
   `requests.get()`
2. Parses the HTML with BeautifulSoup to extract match cards
   (`.tc-match` divs)
3. For each card, pulls out: player names, countries, seeds, set scores,
   tiebreaks, game scores
4. Keeps an **in-memory cache** — when a live match disappears from the
   page (meaning it finished), the cache promotes it to RESULT status so
   it stays visible
5. If no real results exist yet, **seeds sample data** (Alcaraz, Sinner,
   Sabalenka, etc.) so the demo always has something to show
6. If the site is completely unreachable, falls back to the full sample
   dataset

> **About web scraping**: Many sports sites render data with JavaScript
> (React/Vue), meaning the raw HTML might be empty. tennis.com happens
> to include match data in the initial HTML, which is why simple scraping
> works here. For JS-heavy sites, you would need a headless browser
> (Selenium/Playwright) or an official API.

---

## Deploying to Render (free tier)

This repo includes a `render.yaml` Blueprint spec — Render reads it to
auto-configure the service with zero manual settings.

### One-click deploy

1. Push this repo to GitHub (already done).
2. Go to [dashboard.render.com](https://dashboard.render.com/).
3. Click **New → Blueprint**.
4. Connect the **tennis-scores** repo.
5. Render detects `render.yaml`, shows the config — click **Apply**.
6. Wait ~60 seconds for the build. Your app is live at
   `https://tennis-scores-XXXX.onrender.com`.

### What the Blueprint configures

| Setting | Value | Why |
|---------|-------|-----|
| Runtime | Python 3.11 | Pinned via `PYTHON_VERSION` env var |
| Build command | `pip install -r requirements.txt` | Installs Flask, requests, bs4, gunicorn |
| Start command | `gunicorn app:app --bind 0.0.0.0:$PORT` | Render injects `$PORT` automatically |
| Plan | Free | $0 — sleeps after 15 min of inactivity |
| Auto-deploy | Yes | Every push to `main` triggers a redeploy |

### Free-tier notes

- The service **sleeps after 15 minutes of no traffic**. First request
  after sleep takes ~30 seconds to cold-start.
- The in-memory match cache (`_match_cache`) **survives between
  requests** as long as the service stays awake — unlike Vercel where
  each request is a separate function invocation.
- If you need the cache to persist across cold starts, swap it for a
  free Redis add-on (Render offers one) or Upstash.

### Manual deploy (any Linux server)

```bash
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:8000
```

---

## License

MIT — use this however you like.
