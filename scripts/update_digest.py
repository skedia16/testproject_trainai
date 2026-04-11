#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime

try:
  from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
  ZoneInfo = None

import feedparser

try:
  from bs4 import BeautifulSoup
except Exception:
  BeautifulSoup = None


TOPICS = {
  "ai": {
    "label": "AI & tech",
    "feeds": [
      "https://news.google.com/rss/search?q=(artificial+intelligence+OR+OpenAI+OR+Anthropic+OR+DeepMind)+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
      "https://news.google.com/rss/search?q=(NVIDIA+OR+TSMC+OR+chips)+AI+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
  },
  "startups": {
    "label": "Startups & VC",
    "feeds": [
      "https://news.google.com/rss/search?q=(startup+funding+OR+Series+A+OR+venture+capital+OR+acquisition)+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
      "https://news.google.com/rss/search?q=(AI+startup+funding+OR+seed+round)+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
  },
  "india": {
    "label": "India business",
    "feeds": [
      "https://news.google.com/rss/search?q=(India+economy+OR+RBI+OR+inflation+OR+GDP)+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
      "https://news.google.com/rss/search?q=(India+stock+market+OR+Sensex+OR+Nifty)+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
  },
}

N_PER_TOPIC = int(os.environ.get("DIGEST_ITEMS_PER_TOPIC", "4"))


def strip_html(text: str) -> str:
  if not text:
    return ""
  if BeautifulSoup is not None:
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
  text = re.sub(r"<[^>]+>", " ", text)
  return re.sub(r"\s+", " ", text).strip()


def two_sentences(text: str) -> str:
  text = strip_html(text)
  text = re.sub(r"\s+", " ", text).strip()
  if not text:
    return ""
  parts = re.split(r"(?<=[.!?])\s+", text)
  parts = [p.strip() for p in parts if p.strip()]
  if len(parts) >= 2:
    out = " ".join(parts[:2])
  else:
    out = parts[0]
  if len(out) > 280:
    out = out[:277].rstrip() + "…"
  return out


def published_label(entry) -> str:
  ts = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
  if not ts:
    return ""
  try:
    dt = datetime(*ts[:6])
  except Exception:
    return ""
  return dt.strftime("%b %-d") if "%" in "%-d" else dt.strftime("%b %d").replace(" 0", " ")


def parse_google_title(title: str):
  # Google News RSS titles often look like: "Headline - Source"
  if " - " in title:
    headline, source = title.rsplit(" - ", 1)
    return headline.strip(), source.strip()
  return title.strip(), ""


def unique_by_url(items):
  seen = set()
  out = []
  for it in items:
    url = (it.get("url") or "").strip()
    key = url.split("#", 1)[0]
    if not key or key in seen:
      continue
    seen.add(key)
    out.append(it)
  return out


def fetch_topic(topic_id: str):
  topic = TOPICS[topic_id]
  collected = []
  for feed_url in topic["feeds"]:
    parsed = feedparser.parse(feed_url)
    for e in getattr(parsed, "entries", []) or []:
      raw_title = (getattr(e, "title", "") or "").strip()
      title, source = parse_google_title(raw_title)
      url = (getattr(e, "link", "") or "").strip()
      summary = two_sentences(getattr(e, "summary", "") or getattr(e, "description", "") or "")
      published = published_label(e)
      if not title or not url:
        continue
      if not summary:
        summary = "Key details in the article; tap through for full context."
      collected.append(
        {
          "topicId": topic_id,
          "title": title,
          "summary": summary,
          "source": source or topic["label"],
          "url": url,
          "published": published,
        }
      )
  collected = unique_by_url(collected)
  return collected[:N_PER_TOPIC]


def ist_now_iso():
  if ZoneInfo is None:
    return datetime.utcnow().isoformat(timespec="minutes") + "Z"
  dt = datetime.now(ZoneInfo("Asia/Kolkata"))
  return dt.isoformat(timespec="minutes")


def update_html(path: str, articles):
  html = open(path, "r", encoding="utf-8").read()

  build_info = {"generatedAtIso": ist_now_iso(), "timezoneLabel": "IST"}
  build_js = "const BUILD_INFO = " + json.dumps(build_info, ensure_ascii=False, indent=2) + ";\n"

  articles_js = "const ARTICLES = " + json.dumps(articles, ensure_ascii=False, indent=2) + ";\n"

  build_pat = re.compile(r"const\s+BUILD_INFO\s*=\s*\{[\s\S]*?\};\s*", re.M)
  articles_pat = re.compile(r"const\s+ARTICLES\s*=\s*\[[\s\S]*?\];\s*", re.M)

  if not build_pat.search(html):
    raise RuntimeError("Could not find BUILD_INFO block in HTML.")
  if not articles_pat.search(html):
    raise RuntimeError("Could not find ARTICLES array in HTML.")

  html = build_pat.sub(build_js, html, count=1)
  html = articles_pat.sub(articles_js, html, count=1)

  open(path, "w", encoding="utf-8").write(html)


def main():
  html_path = os.environ.get("DIGEST_HTML_PATH", "index.html")
  if not os.path.exists(html_path):
    print(f"Missing file: {html_path}", file=sys.stderr)
    return 2

  articles = []
  for topic_id in ("ai", "startups", "india"):
    articles.extend(fetch_topic(topic_id))

  if len(articles) < 6:
    print("Warning: fetched unusually few articles; check RSS availability.", file=sys.stderr)

  update_html(html_path, articles)
  print(f"Updated {html_path} with {len(articles)} items.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

