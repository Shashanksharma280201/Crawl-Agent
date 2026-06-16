"""Facebook: Saved items. (No clean 'likes' list — bookmarks only.) The saved
page virtualizes, so the engine extracts while scrolling. URL is fixed.

Note: Facebook's markup is heavily obfuscated/randomized; this extractor keys off
durable permalink URL patterns and is best-effort — expect to tune it live.
"""
from collector.platforms.base import Collection, Platform

# Saved items link to post/video permalinks. Class names are randomized, so match
# on durable href patterns and use the anchor text as a best-effort title.
_EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  const sel = 'a[href*="/posts/"], a[href*="story_fbid"], a[href*="/permalink/"], a[href*="/videos/"], a[href*="/photo"]';
  for (const a of document.querySelectorAll(sel)) {
    let href = a.getAttribute('href') || '';
    if (!href) continue;
    const url = href.startsWith('http') ? href : ('https://www.facebook.com' + href);
    const key = url.split('?')[0];
    if (seen.has(key)) continue;
    const txt = a.textContent.trim();
    if (txt.length < 8) continue;
    seen.add(key);
    out.push({ type: 'item', title: txt.slice(0, 180), author: null, url, meta: '' });
  }
  return out;
})()
"""

PLATFORM = Platform(
    key="facebook", name="Facebook", color="#1877F2", blurb="Saved items",
    domain="facebook.com", auth_cookie="c_user",
    login_url="https://www.facebook.com/login",
    collections=(
        Collection(key="saved", name="Saved", kind="bookmarks",
                   url="https://www.facebook.com/saved", nav="scroll",
                   extract_js=_EXTRACT_JS),
    ),
)
