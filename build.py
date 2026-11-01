"""content/*.json -> public/ (statik sayt: xəbərlər, kateqoriyalar, sitemap, RSS)."""
import glob
import json
import os
import shutil
from datetime import datetime, timedelta, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from common import slugify

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public")

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
          "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]


def fmt_date(iso):
    d = datetime.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}, {d:%H:%M}"


env = Environment(
    loader=FileSystemLoader(os.path.join(ROOT, "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)
env.filters["date_az"] = fmt_date


def write(path, html):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(html)


def load_articles():
    items = []
    for p in glob.glob(os.path.join(ROOT, "content", "*.json")):
        with open(p, encoding="utf-8") as f:
            a = json.load(f)
        if a.get("status", "published") != "published":
            continue
        a["url"] = f"/xeber/{a['slug']}/"
        a["cat_slug"] = slugify(a["category"])
        items.append(a)
    items.sort(key=lambda a: a["published"], reverse=True)
    return items


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    shutil.copytree(os.path.join(ROOT, "static"), OUT, dirs_exist_ok=True)

    articles = load_articles()
    cats = {}
    for a in articles:
        cats.setdefault(a["cat_slug"], {"name": a["category"], "slug": a["cat_slug"], "items": []})
        cats[a["cat_slug"]]["items"].append(a)
    nav = sorted(cats.values(), key=lambda c: c["name"])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ctx = dict(cfg=config, nav=nav, now=now)

    write("index.html", env.get_template("index.html").render(
        **ctx, articles=articles[:30], page_title=config.SITE_NAME,
        page_desc=config.SITE_TAGLINE, canonical="/"))

    for a in articles:
        related = [x for x in cats[a["cat_slug"]]["items"] if x["id"] != a["id"]][:4]
        write(f"xeber/{a['slug']}/index.html", env.get_template("article.html").render(
            **ctx, a=a, related=related, page_title=a["title"],
            page_desc=a["description"], canonical=a["url"]))

    for c in cats.values():
        write(f"kateqoriya/{c['slug']}/index.html", env.get_template("category.html").render(
            **ctx, cat=c, articles=c["items"][:60], page_title=c["name"],
            page_desc=f"{c['name']} xəbərləri — {config.SITE_NAME}",
            canonical=f"/kateqoriya/{c['slug']}/"))

    pages = {
        "haqqimizda": ("Haqqımızda", "about.html"),
        "redaksiya-siyaseti": ("Redaksiya siyasəti", "policy.html"),
        "elaqe": ("Əlaqə", "contact.html"),
    }
    for slug, (title, tpl) in pages.items():
        write(f"{slug}/index.html", env.get_template(tpl).render(
            **ctx, page_title=title, page_desc=title + " — " + config.SITE_NAME,
            canonical=f"/{slug}/"))
    write("404.html", env.get_template("404.html").render(
        **ctx, page_title="Səhifə tapılmadı", page_desc="", canonical="/404.html"))

    recent_cut = datetime.now(timezone.utc) - timedelta(days=2)
    recent = [a for a in articles if datetime.fromisoformat(a["published"]) > recent_cut]
    write("sitemap.xml", env.get_template("sitemap.xml").render(
        cfg=config, articles=articles, cats=nav, pages=list(pages), now=now))
    write("news-sitemap.xml", env.get_template("news-sitemap.xml").render(
        cfg=config, articles=recent))
    write("rss.xml", env.get_template("rss.xml").render(
        cfg=config, articles=articles[:30], now=now))
    write("robots.txt",
          f"User-agent: *\nAllow: /\n\nSitemap: {config.SITE_URL}/sitemap.xml\n"
          f"Sitemap: {config.SITE_URL}/news-sitemap.xml\n")
    print(f"Hazırdır: {len(articles)} xəbər, {len(cats)} kateqoriya -> public/")


if __name__ == "__main__":
    main()
