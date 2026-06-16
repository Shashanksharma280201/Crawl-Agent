"""X / Twitter: Bookmarks (default) + Likes (optional).

Both timelines virtualize heavily, so the engine extracts incrementally while
scrolling. The Likes page needs the logged-in username resolved at runtime.
"""
from collector.platforms.base import Collection, Platform

# A bookmarked/liked tweet is an <article data-testid="tweet">. The canonical
# permalink is the timestamp link (.../status/<id>); the author handle is the
# first path segment of that permalink.
_EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  for (const art of document.querySelectorAll('article[data-testid="tweet"]')) {
    const timeA = art.querySelector('a[href*="/status/"] time');
    const link = timeA ? timeA.closest('a') : art.querySelector('a[href*="/status/"]');
    const href = link ? link.getAttribute('href') : null;
    if (!href) continue;
    const id = (href.match(/\/status\/(\d+)/) || [])[1];
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const handle = (href.match(/^\/?([^\/]+)\/status\//) || [])[1];
    const textEl = art.querySelector('div[data-testid="tweetText"]');
    const title = textEl ? textEl.textContent.trim()
                         : (art.textContent.trim().slice(0, 140) || '(no text)');
    out.push({
      type: 'tweet', title,
      author: handle ? '@' + handle : null,
      url: href.startsWith('http') ? href : ('https://x.com' + href),
      meta: '',
    });
  }
  return out;
})()
"""

_USERNAME_JS = ("(()=>{const a=document.querySelector('a[data-testid=\"AppTabBar_Profile_Link\"]');"
                "return a?a.getAttribute('href').replace(/\\//g,''):''})()")

PLATFORM = Platform(
    key="twitter", name="X / Twitter", color="#1D9BF0", blurb="Bookmarks & Likes",
    domain="x.com", auth_cookie="auth_token",
    login_url="https://x.com/i/flow/login",
    needs_username=True, username_js=_USERNAME_JS,
    collections=(
        Collection(key="bookmarks", name="Bookmarks", kind="bookmarks",
                   url="https://x.com/i/bookmarks", nav="scroll", extract_js=_EXTRACT_JS),
        Collection(key="likes", name="Likes", kind="likes",
                   url="https://x.com/{username}/likes", nav="scroll", extract_js=_EXTRACT_JS),
    ),
)
