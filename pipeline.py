"""RSS-dən yeni xəbərləri çəkir, Claude ilə öz sözləri ilə qısa xəbər halına salır,
content/ qovluğuna JSON kimi yazır. Mənbə linki həmişə saxlanır."""
import glob
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

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


class _Paras(HTMLParser):
    """Səhifədən mətni yığır: əvvəl <p> abzasları, olmasa uzun mətn parçaları."""
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "noscript", "form", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_p = False
        self.buf = []
        self.paras = []
        self.loose = []
        self.image = ""

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            d = {k: (v or "") for k, v in attrs}
            key = (d.get("property") or d.get("name") or "").lower()
            if key in ("og:image", "twitter:image") and not self.image:
                self.image = d.get("content", "").strip()
        elif tag in self.SKIP:
            self.skip += 1
        elif tag == "p" and not self.skip:
            self.in_p = True
            self.buf = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "p" and self.in_p:
            self.in_p = False
            t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if len(t) >= 60 and t not in self.paras:
                self.paras.append(t)

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_p:
            self.buf.append(data)
        else:
            t = re.sub(r"\s+", " ", data).strip()
            if len(t) >= 80 and t not in self.loose:
                self.loose.append(t)


def _download(url):
    """Səhifəni açır, (mətn, şəkil_linki) qaytarır."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; newsbot/1.0)",
        "Accept-Language": "az,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        final = resp.geturl()
        if urlparse(final).path in ("", "/"):
            print("  Səhifə ana səhifəyə yönləndi:", url)
            return "", ""
        charset = resp.headers.get_content_charset() or "utf-8"
        html = resp.read(2_000_000).decode(charset, errors="replace")
    p = _Paras()
    p.feed(html)
    text = " ".join(p.paras)
    if len(text) < 200:  # <p> az çıxdı, uzun mətn parçalarını da götür
        text = " ".join(p.paras + p.loose)
    image = urljoin(final, p.image) if p.image else ""
    if not image.startswith(("http://", "https://")) or any(
            w in image.lower() for w in ("logo", "placeholder", "default")):
        image = ""  # loqo və boş şəkilləri götürmə
    print(f"  Səhifə oxundu: {len(p.paras)} abzas, {len(text)} simvol, şəkil: {'var' if image else 'yox'}")
    return text[:4000], image


def fetch_article(url):
    """Xəbər səhifəsindən (mətn, şəkil) çıxarır. Alınmasa boş qaytarır."""
    # lent.az RSS linklərinin sonundakı /1 ana səhifəyə yönləndirir: əvvəl onsuz yoxla
    candidates = []
    clean = re.sub(r"/1/?$", "", url)
    if clean != url:
        candidates.append(clean)
    candidates.append(url)
    best_text, best_image = "", ""
    for u in candidates:
        try:
            text, image = _download(u)
        except Exception as ex:
            print("  Səhifə açılmadı:", u, ex, file=sys.stderr)
            continue
        if len(text) > len(best_text):
            best_text = text
        best_image = best_image or image
        if len(best_text) >= 200 and best_image:
            break
    return best_text, best_image


def backfill_images(limit=10):
    """Şəkli olmayan köhnə xəbərlərə şəkil əlavə edir (hər dəfə ən çox `limit` dənə)."""
    done = 0
    for p in sorted(glob.glob(os.path.join(CONTENT, "*.json"))):
        if done >= limit:
            break
        try:
            with open(p, encoding="utf-8") as f:
                art = json.load(f)
        except Exception:
            continue
        if "image" in art or not art.get("source_url"):
            continue
        _, image = fetch_article(art["source_url"])
        art["image"] = image
        with open(p, "w", encoding="utf-8") as f:
            json.dump(art, f, ensure_ascii=False, indent=2)
        done += 1
        time.sleep(1)
    if done:
        print("Köhnə xəbərlərə şəkil yoxlandı:", done)


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
    backfill_images()
    seen = known_ids()
    created = 0

    for url, category in feeds:
        if created >= config.MAX_PER_RUN:
            break
        parsed = feedparser.parse(url)
        source_name = strip_html(parsed.feed.get("title", "")) or url
        print("Lent:", url, "->", len(parsed.entries), "yazı", parsed.get("bozo_exception", ""))
        taken = 0
        tries = 0
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
            tries += 1
            if tries > 15:  # bir dəfəyə çox səhifə açma
                break
            page_text, image = fetch_article(link)  # tam mətn və şəkil üçün səhifəni aç
            time.sleep(1)
            if len(raw) < 200 and len(page_text) > len(raw):
                raw = page_text
            if len(raw) < 200:
                print("Qısa mətn, keçildi:", len(raw), "simvol", link)
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
                "image": image,
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
