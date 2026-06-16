"""Instagram: Saved (default) + Liked (optional). Both grids virtualize, so the
engine extracts while scrolling. Saved needs the logged-in username; the Liked
'your activity' page does not.

Note: Instagram has aggressive anti-bot; results are best-effort and may need
selector tuning over time.
"""
from collector.platforms.base import Collection, Platform

# Posts/reels are <a href=".../p/<code>/"> or ".../reel/<code>/"> wrapping an
# <img> (alt is the auto-caption). Dedup by shortcode.
_EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\/(p|reel)\/([^\/]+)/);
    if (!m || seen.has(m[2])) continue;
    seen.add(m[2]);
    const img = a.querySelector('img');
    const alt = img ? (img.getAttribute('alt') || '').trim() : '';
    const src = img ? (img.getAttribute('src') || '') : '';
    out.push({
      type: m[1] === 'reel' ? 'reel' : 'post',
      title: alt.slice(0, 160) || (m[1] === 'reel' ? 'Reel' : 'Post'),
      author: null,
      url: 'https://www.instagram.com' + (href.startsWith('/') ? href : ('/' + href)),
      meta: '',
      thumbnail: src.startsWith('http') ? src : null,
    });
  }
  return out;
})()
"""

_USERNAME_JS = ("(()=>{const a=[...document.querySelectorAll('a[href^=\"/\"]')]"
                ".find(x=>/^\\/[a-zA-Z0-9._]+\\/$/.test(x.getAttribute('href')||'')&&x.querySelector('img'));"
                "return a?a.getAttribute('href').replace(/\\//g,''):''})()")

PLATFORM = Platform(
    key="instagram", name="Instagram", color="#E1306C", blurb="Saved & Liked",
    domain="instagram.com", auth_cookie="sessionid",
    login_url="https://www.instagram.com/accounts/login/",
    needs_username=True, username_js=_USERNAME_JS,
    collections=(
        Collection(key="saved", name="Saved", kind="bookmarks",
                   url="https://www.instagram.com/{username}/saved/", nav="scroll",
                   extract_js=_EXTRACT_JS),
        Collection(key="liked", name="Liked", kind="likes",
                   url="https://www.instagram.com/your_activity/interactions/likes/",
                   nav="scroll", extract_js=_EXTRACT_JS),
    ),
)
