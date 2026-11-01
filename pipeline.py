"""RSS-dən yeni xəbərləri çəkir, Claude ilə öz sözləri ilə qısa xəbər halına salır,
content/ qovluğuna JSON kimi yazır. Mənbə linki həmişə saxlanır."""
import glob
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import feedparser
import config
from common import slugify

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
os.makedirs(CONTENT, exist_ok=True)

SYSTEM = f"""Sən {config.LANG_NAME}ndə yazan təcrübəli xəbər redaktorusan.
Sənə mənbədən başlıq və qısa mətn verilir. Bunu oxucu üçün qısa xəbər halına sal.

Qaydalar:
- Yalnız verilən mətndəki faktlardan istifadə et. Heç nə uydurma, təxmin etmə, rəqəm əlavə etmə.
- Mənbənin cümlələrini köçürmə. Hər şeyi tam öz sözlərinlə, fərqli cümlə quruluşu ilə yaz.
- Birbaşa sitat gətirmə (lazım olsa, 5 sözdən çox olmasın).
- İlk abzasda əsas fakt: kim, nə, harada, nə vaxt.
- Mətn xəbər yazmaq üçün çox azdırsa və ya aydın deyilsə, {{"skip": true}} qaytar.
- Cavab YALNIZ JSON olsun, başqa heç nə yazma.

JSON formatı:
{{"title": "60 simvola qədər, informativ başlıq",
  "description": "150 simvola qədər meta təsvir",
  "body": ["1-ci abzas", "2-ci abzas", "istəyə bağlı 3-cü abzas"],
  "key_points": ["qısa məqam 1", "qısa məqam 2"]}}"""


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def load_feeds():
    feeds = []
    with open(os.path.join(ROOT, "feeds.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            url, _, cat = line.partition("|")
            feeds.append((url.strip(), cat.strip() or "Gündəm"))
    return feeds


def known_ids():
    ids = set()
    for p in glob.glob(os.path.join(CONTENT, "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                ids.add(json.load(f)["id"])
        except Exception:
            pass
    return ids


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def make_client():
    if config.AI_PROVIDER == "claude":
        from anthropic import Anthropic
        return Anthropic()  # ANTHROPIC_API_KEY
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def rewrite(client, title, text):
    prompt = f"Mənbə başlığı: {title}\n\nMənbə mətni: {text}"
    if config.AI_PROVIDER == "claude":
        msg = client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=1200, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(msg.content[0].text)

    from google.genai import types
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        max_output_tokens=1500,
    )
    for attempt in range(3):  # pulsuz planda 429 (limit) çıxa bilər
        try:
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL, contents=prompt, config=cfg)
            time.sleep(6)  # dəqiqədə sorğu limitinə sığmaq üçün
            return parse_json(resp.text)
        except Exception as ex:
            if attempt == 2:
                raise
            print("Gözlənilir (limit?):", ex, file=sys.stderr)
            time.sleep(30)


def main():
    feeds = load_feeds()
    if not feeds:
        print("feeds.txt boşdur. RSS linklərini əlavə et.")
        return
    client = make_client()
    seen = known_ids()
    created = 0

    for url, category in feeds:
        if created >= config.MAX_PER_RUN:
            break
        parsed = feedparser.parse(url)
        source_name = strip_html(parsed.feed.get("title", "")) or url
        taken = 0
        for e in parsed.entries:
            if created >= config.MAX_PER_RUN or taken >= config.PER_FEED:
                break
            link = e.get("link")
            if not link:
                continue
            aid = hashlib.sha1(link.encode()).hexdigest()[:10]
            if aid in seen:
                continue
            raw = strip_html(
                (e.get("content") or [{}])[0].get("value") or e.get("summary", "")
            )
            if len(raw) < 200:  # çox qısa mətndən keyfiyyətli xəbər çıxmır
                continue
            try:
                data = rewrite(client, strip_html(e.get("title", "")), raw[:4000])
            except Exception as ex:
                print("Xəta:", link, ex, file=sys.stderr)
                continue
            if data.get("skip") or not data.get("title") or not data.get("body"):
                continue

            article = {
                "id": aid,
                "slug": f"{slugify(data['title'])}-{aid[:5]}",
                "title": data["title"].strip(),
                "description": data.get("description", "").strip(),
                "body": [p.strip() for p in data["body"] if p.strip()],
                "key_points": [k.strip() for k in data.get("key_points", []) if k.strip()],
                "category": category,
                "source_name": source_name,
                "source_url": link,
                "published": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "draft" if config.REVIEW_MODE else "published",
            }
            with open(os.path.join(CONTENT, f"{aid}.json"), "w", encoding="utf-8") as f:
                json.dump(article, f, ensure_ascii=False, indent=2)
            seen.add(aid)
            created += 1
            taken += 1
            print("Yeni:", article["title"])

    print(f"Cəmi yeni xəbər: {created}")


if __name__ == "__main__":
    main()
