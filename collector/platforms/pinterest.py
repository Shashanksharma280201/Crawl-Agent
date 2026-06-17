"""Pinterest: Saved pins. (Pinterest removed 'likes' years ago — bookmarks only.)

The saved page is a virtualized masonry grid, so the engine extracts while
scrolling. The saved URL needs the logged-in username resolved at runtime.
"""
from collector.platforms.base import Collection, Platform

# Each pin is an <a href=".../pin/<id>/"> wrapping a thumbnail <img>. Dedup by id.
_EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/pin/"]')) {
    const m = (a.getAttribute('href') || '').match(/\/pin\/(\d+)/);
    if (!m || seen.has(m[1])) continue;
    seen.add(m[1]);
    const img = a.querySelector('img');
    let alt = img ? (img.getAttribute('alt') || '').trim() : '';
    // Pinterest auto-prefixes image alt text ("This contains an image of: …",
    // "This may contain: …"). Strip the boilerplate to recover the real caption.
    alt = alt.replace(/^(this contains an image of:|this may contain:)\s*/i, '').trim();
    const src = img ? (img.getAttribute('src') || '') : '';
    const label = (a.getAttribute('aria-label') || '').trim();
    out.push({
      type: 'pin',
      title: alt || label || a.textContent.trim().slice(0, 120) || 'Pin',
      author: null,
      url: 'https://www.pinterest.com/pin/' + m[1] + '/',
      meta: '',
      thumbnail: src.startsWith('http') ? src : null,
    });
  }
  return out;
})()
"""

_USERNAME_JS = ("(()=>{let a=document.querySelector(\"a[aria-label*='profile' i]\");"
                "if(a)return a.getAttribute('href').replace(/\\//g,'');"
                "const ls=[...new Set([...document.querySelectorAll('a[href^=\"/\"]')]"
                ".map(x=>x.getAttribute('href')).filter(h=>/^\\/[a-zA-Z0-9._-]+\\/$/.test(h)))];"
                "return ls.length?ls[0].replace(/\\//g,''):'';})()")

PLATFORM = Platform(
    key="pinterest", name="Pinterest", color="#E60023", blurb="Saved pins",
    domain="pinterest.com", auth_cookie="_pinterest_sess",
    login_url="https://www.pinterest.com/login",
    needs_username=True, username_js=_USERNAME_JS,
    collections=(
        Collection(key="saved", name="Saved", kind="bookmarks",
                   url="https://www.pinterest.com/{username}/_saved/", nav="scroll",
                   extract_js=_EXTRACT_JS),
    ),
)
