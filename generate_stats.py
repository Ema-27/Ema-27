#!/usr/bin/env python3
"""Genera SVG con le statistiche GitHub (overview + linguaggi), tema scuro e chiaro.

Solo libreria standard. Variabili d'ambiente:
  ACCESS_TOKEN     PAT con scope read:user + repo (per includere i repo privati)
                   se assente si usa GITHUB_TOKEN (solo dati pubblici)
  GITHUB_USER      username (default: Ema-27)
  INCLUDE_PRIVATE  "true"/"false" (default: true)
  EXCLUDED_LANGS   lingue da ignorare, separate da virgola (es. "HTML,CSS")
  EXCLUDED_REPOS   repo da ignorare, separati da virgola
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from html import escape

API = "https://api.github.com/graphql"
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
USER = os.environ.get("GITHUB_USER", "Ema-27")
INCLUDE_PRIVATE = os.environ.get("INCLUDE_PRIVATE", "true").lower() == "true"


def _set(name):
    return {x.strip().lower() for x in os.environ.get(name, "").split(",") if x.strip()}


EXCLUDED_LANGS = _set("EXCLUDED_LANGS")
EXCLUDED_REPOS = _set("EXCLUDED_REPOS")
OUT = "generated"

THEMES = {
    "dark": dict(bg="#1a1b27", border="#2f3146", title="#70a5fd", text="#a9b1d6", value="#c0caf5", track="#2f3146"),
    "light": dict(bg="#ffffff", border="#d0d7de", title="#0969da", text="#57606a", value="#1f2328", track="#e6e8eb"),
}


def gql(query, variables=None):
    if not TOKEN:
        sys.exit("Nessun token: imposta ACCESS_TOKEN o GITHUB_TOKEN")
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if data.get("errors"):
        sys.exit(f"Errore GraphQL: {data['errors']}")
    return data["data"]


PROFILE_Q = """
query($login:String!){ user(login:$login){
  name login createdAt
  followers{totalCount}
  pullRequests{totalCount}
  issues{totalCount}
  repositoriesContributedTo(first:1, contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY]){totalCount}
}}"""

REPOS_Q = """
query($login:String!, $cursor:String, $privacy:RepositoryPrivacy){ user(login:$login){
  repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false, privacy:$privacy){
    pageInfo{hasNextPage endCursor}
    nodes{ nameWithOwner name stargazerCount forkCount
      languages(first:15, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name color } } }
    }
  }
}}"""

YEAR_Q = """
query($login:String!, $from:DateTime!, $to:DateTime!){ user(login:$login){
  contributionsCollection(from:$from, to:$to){ totalCommitContributions restrictedContributionsCount }
}}"""


def fetch_repos():
    repos, cursor = [], None
    privacy = None if INCLUDE_PRIVATE else "PUBLIC"
    while True:
        d = gql(REPOS_Q, {"login": USER, "cursor": cursor, "privacy": privacy})["user"]["repositories"]
        repos += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            return repos
        cursor = d["pageInfo"]["endCursor"]


def fetch_commits(created_year):
    total = 0
    now = datetime.now(timezone.utc)
    for y in range(created_year, now.year + 1):
        c = gql(YEAR_Q, {"login": USER, "from": f"{y}-01-01T00:00:00Z", "to": f"{y}-12-31T23:59:59Z"})
        c = c["user"]["contributionsCollection"]
        total += c["totalCommitContributions"]
        if INCLUDE_PRIVATE:
            total += c["restrictedContributionsCount"]
    return total


def collect():
    p = gql(PROFILE_Q, {"login": USER})["user"]
    repos = [r for r in fetch_repos() if r["name"].lower() not in EXCLUDED_REPOS
             and r["nameWithOwner"].lower() not in EXCLUDED_REPOS]
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n.lower() in EXCLUDED_LANGS:
                continue
            cur = langs.setdefault(n, {"size": 0, "color": e["node"]["color"] or "#8b949e"})
            cur["size"] += e["size"]
    stats = {
        "name": p["name"] or p["login"],
        "Stelle ricevute": sum(r["stargazerCount"] for r in repos),
        "Fork ricevuti": sum(r["forkCount"] for r in repos),
        "Commit totali": fetch_commits(int(p["createdAt"][:4])),
        "Pull request": p["pullRequests"]["totalCount"],
        "Issue aperte da me": p["issues"]["totalCount"],
        "Repo contribuiti": p["repositoriesContributedTo"]["totalCount"],
        "Follower": p["followers"]["totalCount"],
        "Repository": len(repos),
    }
    return stats, langs


FONT = "font-family: 'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif;"


def frame(w, h, t, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{escape(title)}">\n'
        f'<rect x="0.5" y="0.5" rx="6" width="{w-1}" height="{h-1}" fill="{t["bg"]}" stroke="{t["border"]}"/>\n'
        f'<text x="25" y="35" style="{FONT} font-size:18px; font-weight:600" fill="{t["title"]}">{escape(title)}</text>\n'
        f"{body}</svg>\n"
    )


def overview_svg(stats, t):
    rows = [k for k in stats if k != "name"]
    half = (len(rows) + 1) // 2
    body = []
    for i, k in enumerate(rows):
        col, row = divmod(i, half)
        x = 25 + col * 225
        y = 70 + row * 26
        v = f"{stats[k]:,}".replace(",", ".")
        body.append(
            f'<text x="{x}" y="{y}" style="{FONT} font-size:13px" fill="{t["text"]}">{escape(k)}:</text>'
            f'<text x="{x + 200}" y="{y}" text-anchor="end" style="{FONT} font-size:13px; font-weight:600" '
            f'fill="{t["value"]}">{v}</text>'
        )
    h = 70 + half * 26 + 6
    return frame(495, h, t, f"Statistiche GitHub di {stats['name']}", "\n".join(body) + "\n")


def languages_svg(langs, t, top=8):
    total = sum(v["size"] for v in langs.values()) or 1
    items = sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)[:top]
    shown = sum(v["size"] for _, v in items) or 1
    bar_x, bar_w, bar_y, bar_h = 25, 445, 52, 10
    body = [
        f'<clipPath id="c"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5"/></clipPath>',
        f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5" fill="{t["track"]}"/>',
        '<g clip-path="url(#c)">',
    ]
    x = bar_x
    for name, v in items:
        w = bar_w * v["size"] / shown
        body.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_h}" fill="{v["color"]}"/>')
        x += w
    body.append("</g>")
    half = (len(items) + 1) // 2
    for i, (name, v) in enumerate(items):
        col, row = divmod(i, half)
        lx = 25 + col * 225
        ly = 95 + row * 24
        pct = 100 * v["size"] / total
        body.append(
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{v["color"]}"/>'
            f'<text x="{lx + 18}" y="{ly}" style="{FONT} font-size:13px" fill="{t["text"]}">{escape(name)}</text>'
            f'<text x="{lx + 200}" y="{ly}" text-anchor="end" style="{FONT} font-size:13px; font-weight:600" '
            f'fill="{t["value"]}">{pct:.1f}%</text>'
        )
    h = 95 + half * 24 + 4
    return frame(495, h, t, "Linguaggi più usati", "\n".join(body) + "\n")


def main():
    stats, langs = collect()
    os.makedirs(OUT, exist_ok=True)
    for tname, t in THEMES.items():
        with open(f"{OUT}/overview-{tname}.svg", "w", encoding="utf-8") as f:
            f.write(overview_svg(stats, t))
        with open(f"{OUT}/languages-{tname}.svg", "w", encoding="utf-8") as f:
            f.write(languages_svg(langs, t))
    print(f"Generati 4 SVG in {OUT}/")


if __name__ == "__main__":
    main()
