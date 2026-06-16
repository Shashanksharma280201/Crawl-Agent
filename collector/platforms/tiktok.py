"""TikTok: Favorites (default) + Liked (optional).

Caveat: TikTok exposes Favorites/Liked as TABS on the profile page (not separate
URLs) and the Liked tab is private by default. The engine can't click tabs, so
both collections load the profile and extract whatever video grid is shown — this
is the weakest of the platforms and very likely needs manual tuning / a logged-in
profile with the relevant tab public. Profile URL needs the username resolved.
"""
from collector.platforms.base import Collection, Platform

# Videos are <a href=".../@handle/video/<id>"> wrapping a thumbnail <img>.
_EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/video/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\/video\/(\d+)/);
    if (!m || seen.has(m[1])) continue;
    seen.add(m[1]);
    const img = a.querySelector('img');
    const alt = img ? (img.getAttribute('alt') || '').trim() : '';
    const src = img ? (img.getAttribute('src') || '') : '';
    const handle = (href.match(/\/@([^\/]+)/) || [])[1];
    out.push({
      type: 'video',
      title: alt.slice(0, 160) || 'TikTok video',
      author: handle ? '@' + handle : null,
      url: href.startsWith('http') ? href : ('https://www.tiktok.com' + href),
      meta: '',
      thumbnail: src.startsWith('http') ? src : null,
    });
  }
  return out;
})()
"""

_USERNAME_JS = ("(()=>{const a=document.querySelector('a[href^=\"/@\"]');"
                "return a?a.getAttribute('href').replace('/@','').replace(/\\//g,''):''})()")

PLATFORM = Platform(
    key="tiktok", name="TikTok", color="#25F4EE", blurb="Favorites & Liked",
    domain="tiktok.com", auth_cookie="sessionid",
    login_url="https://www.tiktok.com/login",
    needs_username=True, username_js=_USERNAME_JS,
    collections=(
        Collection(key="favorites", name="Favorites", kind="bookmarks",
                   url="https://www.tiktok.com/@{username}", nav="scroll",
                   extract_js=_EXTRACT_JS),
        Collection(key="liked", name="Liked", kind="likes",
                   url="https://www.tiktok.com/@{username}", nav="scroll",
                   extract_js=_EXTRACT_JS),
    ),
)
