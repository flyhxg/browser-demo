# Binance Square HTML Fixture — Capture Notes

**Captured:** 2026-06-05 (Asia/Shanghai)
**Source URL:** `https://www.binance.com/en/square`
**Tool:** Playwright + chromium (headless), UA `Chrome/127.0.0.0`, viewport 1920x1080
**Wait strategy:** `domcontentloaded` + 5s settle + 2 scroll-downs (1200px each, 2.5s gap)
**Files:**
- `home_with_posts.html` (681,753 bytes) — real feed with 20 posts
- `empty_page.html` (681,753 bytes) — best-effort (same as home; no empty state detected)
- `login_wall.html` (681,753 bytes) — best-effort (no login wall detected)
- `captcha.html` (681,753 bytes) — best-effort (no captcha detected)

**Status:** Capture succeeded. Page rendered the public feed without bot challenge. 20 real posts with full author/content/likes/comments/views metadata. No login wall or captcha was triggered (consistent with the 5s headless wait + scrolled loads — Binance allows anonymous feed reads).

---

## Selectors for Task 5 (`_parse_html`)

### Post card wrapper

Two layers — both are unique per post:

1. **Outer container** (the visible card box, includes the `border-Line border-b` separator):
   ```
   div.FeedBuzzBaseView_FeedBuzzBaseViewRootBox__1fzEU.feed-card
   ```
   Stable attribute selector: `[class*="FeedBuzzBaseViewRootBox"][class*="feed-card"]`

2. **Inner root with `data-id`** (the cleanest per-post anchor — use this one for iteration):
   ```
   div.FeedBuzzBaseViewRoot[data-id="<post_id>"]
   ```
   Stable attribute selector: `[class*="FeedBuzzBaseViewRoot"][data-id]`

> Recommendation: iterate by `[data-id]` — gives a unique post id with no extra parsing, and matches the URL path tail exactly.

### Per-card fields (relative to the inner root)

| Field        | Selector                                                                                              | Sample value                                |
|--------------|-------------------------------------------------------------------------------------------------------|---------------------------------------------|
| Post id      | `[data-id]` attribute on the inner root                                                                | `330020877222706`                            |
| Post URL     | `a[href^="/en/square/post/"]` (the title link; there is also a hidden anchor with `style="display: none;"` that contains the full text and is more parseable) | `/en/square/post/330020877222706`            |
| Post body    | `div.card__description.rich-text` (preferred) — OR `div.feed-content-text a[href^="/en/square/post/"]` text (hidden, contains raw text incl. `<br>`) | "Garrett Jin(@GarrettBullish) nailed the top..." |
| Author nick  | `div.nick-username a.nick[href^="/en/square/profile/"]` — text of the `<a>`                            | `lookonchain`                               |
| Author URL   | `div.nick-username a.nick[href^="/en/square/profile/"]` — `href` attribute                            | `/en/square/profile/lookonchain`            |
| Create time  | `div.create-time` — text                                                                              | `Jun 3` / `19h` / `11h` (Binance relative format) |
| Likes        | `div.thumb-up-button.card-function-item span.current`                                                  | `125`                                       |
| Comments     | `div.comments-icon.card-function-item span.current`                                                    | `14`                                        |
| Views        | `div.view-counts.card-function-item span.current` (some posts may not render views)                   | `1.5M` / `6`                                |
| Image URLs   | `div.images-box-item` (the `<img>` `src` attribute, base64-encoded query string)                       | `/bapi/fe/resource/image?image=...`         |

### Notes for the parser

- **Two `<a href="/en/square/post/...">` per card.** The title link wraps a short preview, and a hidden anchor (`style="display: none;"`) inside `div.feed-content-text` contains the **full** body text (cleaner source for `text`). Pick the hidden anchor for `text`; pick the title link for `url`.
- **Create time is humanised** (`"Jun 3"`, `"19h"`, `"11h"`). To produce an absolute `created_at`, parse against a "now" injected from the caller (Task 6). Examples observed: `"11h"`, `"19h"`, `"Jun 3"`, `"Jun 4"`.
- **Like/comment/view counts are short numbers** (no `K`/`M` suffix in the rendered HTML — those are the display format; the raw `<span class="current">` always has the formatted string, e.g. `"1.5M"`). Treat as strings; convert in Python if you need ints.
- **Class names are partially CSS-modules** (e.g. `FeedBuzzBaseView_FeedBuzzBaseViewRoot__1sC8Q`) AND partially Tailwind utility soup. Use the `class*=` / `class^=` substring selectors rather than exact match.
- **Robust selector for "is this a post card?"**: `[class*="feed-card"][class*="is-card"]` is the post wrapper; `div.FollowListCard` is something else (follow suggestions) — filter that out.

### Counted on capture

- 20 `feed-card` containers
- 20 unique `data-id` values (matching 20 unique post URLs)
- 20 `nick-username` blocks (one per post)
- 20 `thumb-up-button` blocks with `span.current` text
- 20 `comments-icon` blocks with `span.current` text
- 19 `view-counts` blocks (one post had no views rendered)
- 20 `create-time` divs

### Sample post (first one captured)

- `data-id`: `330020877222706`
- URL: `/en/square/post/330020877222706`
- Author: `lookonchain` (`/en/square/profile/lookonchain`)
- Time: `Jun 3`
- Body: starts with "Garrett Jin(@GarrettBullish) nailed the top this time."
- Likes: `125`, Comments: `14`, Views: `1M` (parses as `1000000` if treated as `1.0M`)

---

## Maintenance

Re-run from project root when Binance changes the DOM:

```bash
cd backend && python tests/fixtures/binance_square/capture_fixtures.py
```

The script overwrites the four `.html` files in place.
