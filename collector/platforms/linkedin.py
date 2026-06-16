"""LinkedIn: Saved posts. (LinkedIn has no viewable 'my likes' list — bookmarks
only.) The saved-posts page virtualizes, so the engine extracts while scrolling.
The URL is fixed (no username needed)."""
from collector.platforms.base import Collection, Platform

# Saved posts render as feed-update cards; the durable link is the post permalink
# (/feed/update/... or /posts/...). Use the anchor text as a best-effort title.
_EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/feed/update/"], a[href*="/posts/"]')) {
    let href = a.getAttribute('href') || '';
    if (!href) continue;
    const url = href.startsWith('http') ? href : ('https://www.linkedin.com' + href);
    const key = url.split('?')[0];
    if (seen.has(key)) continue;
    const txt = a.textContent.trim();
    if (txt.length < 8) continue;   // skip icon/avatar links with no text
    seen.add(key);
    out.push({ type: 'post', title: txt.slice(0, 180), author: null, url, meta: '' });
  }
  return out;
})()
"""

PLATFORM = Platform(
    key="linkedin", name="LinkedIn", color="#0A66C2", blurb="Saved posts",
    domain="linkedin.com", auth_cookie="li_at",
    login_url="https://www.linkedin.com/login",
    collections=(
        Collection(key="saved", name="Saved", kind="bookmarks",
                   url="https://www.linkedin.com/my-items/saved-posts/", nav="scroll",
                   extract_js=_EXTRACT_JS),
    ),
)
