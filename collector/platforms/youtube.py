"""YouTube: Watch Later (bookmarks) + Liked videos (likes)."""
from collector.platforms.base import Collection, Platform

# Stall probe: number of rendered video rows (both layouts). More reliable than
# scrollHeight for YouTube's virtualized playlist pages.
_COUNT_JS = ("(() => document.querySelectorAll("
             "'ytd-playlist-video-renderer, yt-lockup-view-model').length)()")

# Returns canonical items: {type,title,author,url,meta}. Handles both the old
# renderer layout and the new lockup layout. Builds absolute watch URLs inline.
_EXTRACT_JS = r"""
(() => {
  const out = [];
  const vid = (h) => { const m = (h||'').match(/[?&]v=([^&]+)/); return m ? m[1] : null; };
  const push = (title, channel, dur, href) => {
    const id = vid(href);
    const url = id ? ('https://www.youtube.com/watch?v=' + id)
              : (href && href.startsWith('/') ? ('https://www.youtube.com' + href) : null);
    if (!url) return;
    out.push({ type: 'video', title: title || null, author: channel || null,
               url, meta: dur || null });
  };
  for (const r of document.querySelectorAll('ytd-playlist-video-renderer')) {
    const a = r.querySelector('a#video-title');
    const ch = r.querySelector('ytd-channel-name a');
    const dur = r.querySelector('ytd-thumbnail-overlay-time-status-renderer #text, #text.ytd-thumbnail-overlay-time-status-renderer, .badge-shape-wiz__text');
    push(a ? (a.getAttribute('title') || a.textContent.trim()) : null,
         ch ? ch.textContent.trim() : null,
         dur ? dur.textContent.trim() : null,
         a ? a.getAttribute('href') : null);
  }
  for (const r of document.querySelectorAll('yt-lockup-view-model')) {
    const a = r.querySelector('a[href*="/watch"]:not(.ytLockupViewModelContentImage)')
           || [...r.querySelectorAll('a[href*="/watch"]')].find(x => x.textContent.trim().length > 6);
    const ch = r.querySelector('a[href^="/@"], a[href*="/channel/"], a[href*="/user/"]');
    let dur = null;
    for (const b of r.querySelectorAll('badge-shape, .badge-shape-wiz__text')) {
      const t = b.textContent.trim();
      if (/^\d{1,2}(:\d{2})+$/.test(t)) { dur = t; break; }
    }
    push(a ? (a.getAttribute('title') || a.textContent.trim()) : null,
         ch ? ch.textContent.trim() : null, dur,
         a ? a.getAttribute('href') : null);
  }
  return out;
})()
"""

PLATFORM = Platform(
    key="youtube", name="YouTube", color="#FF0000", blurb="Watch Later & Liked",
    domain="youtube.com", auth_cookie="LOGIN_INFO",
    login_url="https://www.youtube.com",
    collections=(
        Collection(key="watch_later", name="Watch Later", kind="bookmarks",
                   url="https://www.youtube.com/playlist?list=WL", nav="scroll",
                   extract_js=_EXTRACT_JS, count_js=_COUNT_JS),
        Collection(key="liked", name="Liked videos", kind="likes",
                   url="https://www.youtube.com/playlist?list=LL", nav="scroll",
                   extract_js=_EXTRACT_JS, count_js=_COUNT_JS),
    ),
)
