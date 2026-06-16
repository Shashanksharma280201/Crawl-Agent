"""Reddit: Saved posts & comments (paginated old.reddit)."""
from collector.platforms.base import Collection, Platform

# old.reddit.com/saved auto-redirects to the logged-in user's saved page and
# paginates via a "next" button (server-rendered, no infinite scroll).
_EXTRACT_JS = r"""
(() => {
  const out = [];
  for (const t of document.querySelectorAll('#siteTable div.thing[data-fullname]')) {
    const fn = t.getAttribute('data-fullname');
    const isC = fn.startsWith('t1_');
    const titleEl = t.querySelector('a.title');
    const body = t.querySelector('div.md');
    out.push({
      type: isC ? 'comment' : 'post',
      title: titleEl ? titleEl.textContent.trim()
                     : (body ? body.textContent.trim().slice(0, 140) : fn),
      subreddit: t.getAttribute('data-subreddit') ? 'r/' + t.getAttribute('data-subreddit') : null,
      author: t.getAttribute('data-author') || null,
      url: t.getAttribute('data-permalink')
           ? 'https://www.reddit.com' + t.getAttribute('data-permalink')
           : (t.getAttribute('data-url') || null),
      meta: t.getAttribute('data-score') ? '⬆ ' + t.getAttribute('data-score') : '',
      body: (isC && body) ? body.textContent.trim() : null,
    });
  }
  return out;
})()
"""

_NEXT_JS = "(()=>{const a=document.querySelector('span.next-button a');return a?a.href:''})()"

PLATFORM = Platform(
    key="reddit", name="Reddit", color="#FF4500", blurb="Saved posts & comments",
    domain="reddit.com", auth_cookie="reddit_session",
    login_url="https://www.reddit.com/login",
    collections=(
        Collection(key="saved", name="Saved", kind="bookmarks",
                   url="https://old.reddit.com/saved", nav="paginate",
                   extract_js=_EXTRACT_JS, next_js=_NEXT_JS),
    ),
)
