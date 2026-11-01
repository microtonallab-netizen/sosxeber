# Avtomatik xəbər saytı

RSS-dən xəbər çəkir, Claude ilə öz sözləri ilə qısa xəbər halına salır, statik sayt kimi dərc edir.
Hər xəbərdə mənbə linki, NewsArticle schema, news-sitemap, RSS və canonical var.

## Qurulum (təxminən 15 dəqiqə)

1. GitHub-da yeni repo aç və bu qovluğun içindəkiləri yüklə.
2. `feeds.txt` faylına öz RSS mənbələrini yaz (`link | Kateqoriya`). Yalnız istifadəsinə icazə verən mənbələr.
3. Pulsuz AI açarı: aistudio.google.com saytında "Get API key" ilə Gemini açarı al.
   Repo → Settings → Secrets and variables → Actions → `GEMINI_API_KEY` adlı secret əlavə et.
   (Pullu Claude istəsən: Variables-da `AI_PROVIDER=claude` yaz və `ANTHROPIC_API_KEY` secret-i əlavə et.)
   Model adı köhnəlsə, Variables-da `GEMINI_MODEL` ilə dəyiş (aistudio-da yazılıb).
4. Cloudflare Pages-də həmin repoya qoşul:
   - Build command: `pip install -r requirements.txt && python build.py`
   - Output directory: `public`
   - Environment variables: `SITE_NAME`, `SITE_URL` (məs. https://saytin.az), `CONTACT_EMAIL`
5. Actions → "Xəbərləri yenilə" → Run workflow ilə ilk işə salma. Sonra 2 saatdan bir özü işləyir.
6. Google Search Console-a sayt əlavə et, `sitemap.xml` və `news-sitemap.xml` göndər.

## Faydalı ayarlar (config.py / mühit dəyişənləri)

- `REVIEW_MODE=true` (GitHub repo Variables-da): xəbərlər "draft" gəlir. `content/xxx.json` faylında
  `"status": "published"` etsən dərc olunur. Telefondan GitHub tətbiqi ilə olar.
- `MAX_PER_RUN`, `PER_FEED`: hər dəfə neçə xəbər. Az və keyfiyyətli saxla.
