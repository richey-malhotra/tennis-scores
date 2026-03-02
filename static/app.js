/*
 * Tennis Scores Dashboard — Client-side JavaScript
 * ==================================================
 *
 * HOW IT WORKS
 * ────────────
 * 1. On page load, fetchScores() calls our Flask API (/api/scores).
 * 2. The API returns JSON with an array of match objects.
 * 3. We store those in `allMatches`, then filter/sort/group them
 *    according to the dropdown controls.
 * 4. renderMatches() builds the HTML for each match card and injects
 *    it into the page.  No framework — just template literals.
 *
 * KEY CONCEPTS
 * ────────────
 * - Country flags are built from ISO codes using Unicode regional
 *   indicator symbols (no images needed).
 * - Intensity is a 1-5 rating computed server-side based on how
 *   close the score is.  We visualise it with coloured dot arrays.
 * - Tiebreak scores appear as tiny superscripts on the LOSER's
 *   set score (standard tennis notation).
 */

// ── COUNTRY CODE → EMOJI FLAG ──────────────────────────────────────
// Tennis uses 3-letter codes (USA, GBR) but Unicode flags need 2-letter
// ISO codes.  We map the common ones, then convert each letter to a
// "regional indicator symbol" (Unicode block starting at 0x1F1E6).
// E.g. "US" → 🇺🇸  because U=0x1F1FA, S=0x1F1F8.
function countryFlag(code) {
    if (!code || code.length < 2) return "";
    // Map common 3-letter codes to 2-letter ISO
    const map3to2 = {
        USA: "US", GBR: "GB", FRA: "FR", ESP: "ES", GER: "DE", DEU: "DE",
        ITA: "IT", AUS: "AU", JPN: "JP", CHN: "CN", BRA: "BR", ARG: "AR",
        CAN: "CA", RUS: "RU", SUI: "CH", CHE: "CH", NED: "NL", NLD: "NL",
        BEL: "BE", SWE: "SE", NOR: "NO", DEN: "DK", DNK: "DK", AUT: "AT",
        POL: "PL", CZE: "CZ", GRE: "GR", GRC: "GR", CRO: "HR", HRV: "HR",
        SRB: "RS", UKR: "UA", KAZ: "KZ", GEO: "GE", BUL: "BG", BGR: "BG",
        ROU: "RO", HUN: "HU", POR: "PT", PRT: "PT", RSA: "ZA", ZAF: "ZA",
        KOR: "KR", TPE: "TW", IND: "IN", THA: "TH", COL: "CO", CHI: "CL",
        CHL: "CL", PER: "PE", ECU: "EC", MEX: "MX", TUN: "TN", MAR: "MA",
        BLR: "BY", SVK: "SK", SLO: "SI", SVN: "SI", ISR: "IL", TUR: "TR",
        MNE: "ME", BIH: "BA", LAT: "LV", LVA: "LV", LTU: "LT", EST: "EE",
        FIN: "FI", IRL: "IE", NZL: "NZ",
    };
    const cc = (map3to2[code.toUpperCase()] || code.substring(0, 2)).toUpperCase();
    const base = 0x1f1e6;
    return String.fromCodePoint(base + cc.charCodeAt(0) - 65, base + cc.charCodeAt(1) - 65);
}

// ── INTENSITY HELPERS ──────────────────────────────────────────────
// Convert a 1–5 number into a human-readable word and a row of dots.

function intensityLabel(n) {
    const labels = ["", "Routine", "Competitive", "Close", "Thrilling", "Epic"];
    return labels[Math.min(Math.max(n, 1), 5)];
}

function intensityDots(n) {
    const filled = Math.min(Math.max(n, 0), 5);
    return '<span class="intensity-dots">' +
        Array.from({length: 5}, (_, i) =>
            `<span class="dot ${i < filled ? "filled level-" + filled : ""}"></span>`
        ).join("") + "</span>";
}

// ── APP STATE ─────────────────────────────────────────────────────
// A single array holds every match from the last API call.
// Filter/sort/group functions read from this without mutating it.
let allMatches = [];

// ── FETCH SCORES FROM API ─────────────────────────────────────────
async function fetchScores() {
    const statusBar = document.getElementById("status-bar");
    const btn = document.getElementById("refresh-btn");
    statusBar.textContent = "Fetching scores...";
    statusBar.className = "status-bar loading";
    btn.disabled = true;

    try {
        const resp = await fetch("/api/scores");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        allMatches = data.matches;
        const time = new Date(data.fetched_at).toLocaleTimeString();
        statusBar.textContent = `${data.count} matches loaded at ${time}`;
        statusBar.className = "status-bar success";
        updateSummary();
        renderMatches();
    } catch (err) {
        statusBar.textContent = `Error: ${err.message}`;
        statusBar.className = "status-bar error";
    } finally {
        btn.disabled = false;
    }
}

// ── SUMMARY STATS ─────────────────────────────────────────────────
// Populate the five stat cards at the top of the page.
// All cards respect the current status-filter dropdown so the user
// sees counts for "All", "LIVE", or "RESULT" — not always the full set.
function updateSummary() {
    const filterStatus = document.getElementById("filter-status").value;
    const pool = filterStatus === "all"
        ? allMatches
        : allMatches.filter(m => m.status === filterStatus);

    const total = pool.length;
    const live = pool.filter(m => m.status === "LIVE").length;
    const results = pool.filter(m => m.status === "RESULT").length;
    const countries = new Set();
    pool.forEach(m => {
        if (m.player1.country) countries.add(m.player1.country);
        if (m.player2.country) countries.add(m.player2.country);
    });
    const threeSetters = pool.filter(m =>
        Math.max(m.sets.player1.length, m.sets.player2.length) >= 3
    ).length;
    const hottest = pool.length > 0
        ? pool.reduce((max, m) => m.intensity > max.intensity ? m : max, pool[0])
        : null;

    document.querySelector("#stat-total .stat-num").textContent = total;
    document.querySelector("#stat-live .stat-num").textContent = `${live} live`;
    document.querySelector("#stat-live .stat-detail").textContent = `${results} results`;
    document.querySelector("#stat-countries .stat-num").textContent = countries.size;
    document.querySelector("#stat-threesetters .stat-num").textContent = threeSetters;
    if (hottest) {
        const name = hottest.player1.name.split(" ").pop() + " v " + hottest.player2.name.split(" ").pop();
        document.querySelector("#stat-hottest .stat-num").textContent = name;
    } else {
        document.querySelector("#stat-hottest .stat-num").textContent = "-";
    }
}

// ── FILTER & SORT ─────────────────────────────────────────────────
// Apply the current dropdown selections to produce a display-ready list.
function getProcessed() {
    const filterStatus = document.getElementById("filter-status").value;
    const sortBy = document.getElementById("sort-by").value;

    let matches = [...allMatches];

    // Filter
    if (filterStatus !== "all") {
        matches = matches.filter(m => m.status === filterStatus);
    }

    // Sort
    matches.sort((a, b) => {
        switch (sortBy) {
            case "intensity-desc":
                return b.intensity - a.intensity || statusOrder(a) - statusOrder(b);
            case "status":
                return statusOrder(a) - statusOrder(b) || b.intensity - a.intensity;
            case "seed": {
                const sa = Math.min(a.player1.seed || 999, a.player2.seed || 999);
                const sb = Math.min(b.player1.seed || 999, b.player2.seed || 999);
                return sa - sb;
            }
            case "player":
                return a.player1.name.localeCompare(b.player1.name);
            case "tournament":
                return a.tournament.localeCompare(b.tournament);
            default:
                return 0;
        }
    });

    return matches;
}

function statusOrder(m) {
    return m.status === "LIVE" ? 0 : 1;
}

// ── GROUPING ──────────────────────────────────────────────────────
// Split the filtered list into labelled sections.
function groupMatches(matches) {
    const groupBy = document.getElementById("group-by").value;
    if (groupBy === "none") return [{ label: null, matches }];

    const groups = {};
    for (const m of matches) {
        let key;
        switch (groupBy) {
            case "country":
                // Group by countries involved (a match appears under each player's country)
                key = getCountryGroup(m);
                break;
            case "tournament":
                key = m.tournament;
                break;
            case "status":
                key = m.status;
                break;
            case "intensity":
                key = intensityLabel(m.intensity);
                break;
            case "event":
                key = m.event || "Other";
                break;
        }

        if (groupBy === "country") {
            // A match can appear in multiple country groups
            const countries = getCountries(m);
            for (const c of countries) {
                if (!groups[c]) groups[c] = [];
                groups[c].push(m);
            }
        } else {
            if (!groups[key]) groups[key] = [];
            groups[key].push(m);
        }
    }

    // Sort group keys
    let sortedKeys = Object.keys(groups);
    if (groupBy === "intensity") {
        const order = ["Epic", "Thrilling", "Close", "Competitive", "Routine"];
        sortedKeys.sort((a, b) => order.indexOf(a) - order.indexOf(b));
    } else if (groupBy === "status") {
        const order = ["LIVE", "RESULT"];
        sortedKeys.sort((a, b) => order.indexOf(a) - order.indexOf(b));
    } else {
        sortedKeys.sort();
    }

    return sortedKeys.map(key => ({
        label: groupBy === "country" ? `${countryFlag(key)} ${key}` : key,
        matches: groups[key],
    }));
}

function getCountries(m) {
    const cs = new Set();
    if (m.player1.country) cs.add(m.player1.country);
    if (m.player2.country) cs.add(m.player2.country);
    return [...cs];
}

function getCountryGroup(m) {
    return getCountries(m).join(" / ") || "Unknown";
}

// ── RENDER ────────────────────────────────────────────────────────
// Build the HTML for every visible match and inject it.
function renderMatches() {
    const container = document.getElementById("scores-container");
    const matches = getProcessed();

    if (matches.length === 0) {
        container.innerHTML = '<div class="empty">No matches found.</div>';
        return;
    }

    const groups = groupMatches(matches);
    let html = "";

    for (const group of groups) {
        if (group.label) {
            html += `<div class="group-header">${group.label} <span class="group-count">(${group.matches.length})</span></div>`;
        }
        html += '<div class="match-list">';
        for (const m of group.matches) {
            html += renderMatchRow(m);
        }
        html += "</div>";
    }

    container.innerHTML = html;
}

function renderMatchRow(m) {
    const p1 = m.player1;
    const p2 = m.player2;

    const statusClass = m.status.toLowerCase();
    let statusBadge;
    if (m.status === "LIVE") {
        statusBadge = '<span class="badge live">LIVE</span>';
    } else {
        statusBadge = '<span class="badge result">RESULT</span>';
    }

    const p1Flag = p1.country ? `<span class="flag" title="${p1.country}">${countryFlag(p1.country)}</span>` : "";
    const p2Flag = p2.country ? `<span class="flag" title="${p2.country}">${countryFlag(p2.country)}</span>` : "";

    const p1Seed = p1.seed ? `<span class="seed">[${p1.seed}]</span>` : "";
    const p2Seed = p2.seed ? `<span class="seed">[${p2.seed}]</span>` : "";

    const p1Winner = p1.is_winner ? " winner" : "";
    const p2Winner = p2.is_winner ? " winner" : "";

    // Build set-by-set score display
    const setsHtml = buildSetsHtml(m);

    const hrefAttr = m.url ? `href="${m.url}" target="_blank"` : "";

    return `
    <a ${hrefAttr} class="match-row ${statusClass}">
        <div class="match-status">${statusBadge}</div>
        <div class="match-players">
            <div class="player-line${p1Winner}">
                ${p1Flag}
                <span class="player-name">${p1.name}</span>
                ${p1Seed}
            </div>
            <div class="player-line${p2Winner}">
                ${p2Flag}
                <span class="player-name">${p2.name}</span>
                ${p2Seed}
            </div>
        </div>
        <div class="match-score">
            ${setsHtml}
        </div>
        <div class="match-intensity" title="${intensityLabel(m.intensity)}">
            ${intensityDots(m.intensity)}
            <span class="intensity-label">${intensityLabel(m.intensity)}</span>
        </div>
        <div class="match-meta">
            <span class="meta-tournament">${m.tournament}</span>
            <span class="meta-round">${m.round}${m.event ? " - " + m.event : ""}</span>
        </div>
    </a>`;
}

/**
 * Build the set-by-set score grid (two rows: player 1 / player 2).
 *
 * Tiebreak convention:  In tennis, a tiebreak score is displayed as a
 * small superscript on the LOSER's set score.  For example, a set that
 * ended 7–6 with a 7-3 tiebreak is shown as:
 *
 *   Winner:  7         (no annotation — they won)
 *   Loser:   6³        (superscript 3 = their tiebreak points)
 *
 * The server already places each tiebreak value in the correct player's
 * array, so we just render whatever is there.
 */
function buildSetsHtml(m) {
    const p1Sets = m.sets.player1;
    const p2Sets = m.sets.player2;
    const p1TB = (m.tiebreaks && m.tiebreaks.player1) || [];
    const p2TB = (m.tiebreaks && m.tiebreaks.player2) || [];
    const gameScore = m.game_score || {};
    const maxSets = Math.max(p1Sets.length, p2Sets.length);

    if (maxSets === 0) {
        return '<span class="score-vs">-</span>';
    }

    let html = '<div class="sets-grid">';

    // Row 1: player 1 scores
    html += '<div class="sets-row">';
    for (let i = 0; i < maxSets; i++) {
        const val = p1Sets[i] || "";
        const tb = p1TB[i] || "";
        const isLiveSet = m.status === "LIVE" && i === maxSets - 1;
        const tbHtml = tb ? `<sup class="tiebreak">${tb}</sup>` : "";
        html += `<span class="set-score${isLiveSet ? " live-set" : ""}">${val}${tbHtml}</span>`;
    }
    // Current game score for player 1
    if (gameScore.player1) {
        html += `<span class="game-score">${gameScore.player1}</span>`;
    }
    html += "</div>";

    // Row 2: player 2 scores
    html += '<div class="sets-row">';
    for (let i = 0; i < maxSets; i++) {
        const val = p2Sets[i] || "";
        const tb = p2TB[i] || "";
        const isLiveSet = m.status === "LIVE" && i === maxSets - 1;
        const tbHtml = tb ? `<sup class="tiebreak">${tb}</sup>` : "";
        html += `<span class="set-score${isLiveSet ? " live-set" : ""}">${val}${tbHtml}</span>`;
    }
    // Current game score for player 2
    if (gameScore.player2) {
        html += `<span class="game-score">${gameScore.player2}</span>`;
    }
    html += "</div>";

    html += "</div>";
    return html;
}

// ── EVENT LISTENERS ───────────────────────────────────────────────
// Re-render whenever a dropdown changes (no full re-fetch needed).
// Re-render match list and update summary cards on any dropdown change.
// The filter-status listener calls updateSummary() so all five stat
// cards reflect the active filter (All / LIVE / RESULT).
function onControlChange() { updateSummary(); renderMatches(); }
document.getElementById("group-by").addEventListener("change", onControlChange);
document.getElementById("filter-status").addEventListener("change", onControlChange);
document.getElementById("sort-by").addEventListener("change", onControlChange);

// ── BOOT ──────────────────────────────────────────────────────────
fetchScores();
