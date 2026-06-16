"""Central platform registry — shared by browser.py, collect.py, app.py.

Each platform declares:
  login_url   : where to send the user to sign in (headed, once)
  saved_url   : the saved/bookmarks page ({username} resolved at runtime)
  domain      : cookie/url domain
  auth_cookie : cookie whose presence == logged in (for per-platform detection)
  extractor   : which extraction strategy to use ('youtube' | 'reddit' | 'generic')
  status      : 'solid' (proven) | 'experimental' (generic a11y, may need tuning)
"""

PLATFORMS = [
    {"key": "youtube", "name": "YouTube", "color": "#FF0000", "blurb": "Watch Later & Liked",
     "login_url": "https://www.youtube.com", "saved_url": None, "domain": "youtube.com",
     "auth_cookie": "LOGIN_INFO", "extractor": "youtube", "status": "solid",
     "collector": "collect_youtube.py"},

    {"key": "reddit", "name": "Reddit", "color": "#FF4500", "blurb": "Saved posts & comments",
     "login_url": "https://www.reddit.com/login", "saved_url": "https://old.reddit.com/saved",
     "domain": "reddit.com", "auth_cookie": "reddit_session", "extractor": "reddit", "status": "solid",
     "collector": "collect.py"},

    {"key": "twitter", "name": "X / Twitter", "color": "#1D9BF0", "blurb": "Bookmarks",
     "login_url": "https://x.com/i/flow/login", "saved_url": "https://x.com/i/bookmarks",
     "domain": "x.com", "auth_cookie": "auth_token", "extractor": "generic", "status": "experimental",
     "collector": "collect.py"},

    {"key": "linkedin", "name": "LinkedIn", "color": "#0A66C2", "blurb": "Saved posts",
     "login_url": "https://www.linkedin.com/login", "saved_url": "https://www.linkedin.com/my-items/saved-posts/",
     "domain": "linkedin.com", "auth_cookie": "li_at", "extractor": "generic", "status": "experimental",
     "collector": "collect.py"},

    {"key": "instagram", "name": "Instagram", "color": "#E1306C", "blurb": "Saved posts & reels",
     "login_url": "https://www.instagram.com/accounts/login/", "saved_url": "https://www.instagram.com/{username}/saved/",
     "domain": "instagram.com", "auth_cookie": "sessionid", "extractor": "generic", "status": "experimental",
     "collector": "collect.py"},

    {"key": "tiktok", "name": "TikTok", "color": "#25F4EE", "blurb": "Favorites & liked",
     "login_url": "https://www.tiktok.com/login", "saved_url": "https://www.tiktok.com/@{username}",
     "domain": "tiktok.com", "auth_cookie": "sessionid", "extractor": "generic", "status": "experimental",
     "collector": "collect.py"},

    {"key": "facebook", "name": "Facebook", "color": "#1877F2", "blurb": "Saved items",
     "login_url": "https://www.facebook.com/login", "saved_url": "https://www.facebook.com/saved",
     "domain": "facebook.com", "auth_cookie": "c_user", "extractor": "generic", "status": "experimental",
     "collector": "collect.py"},

    {"key": "pinterest", "name": "Pinterest", "color": "#E60023", "blurb": "Saved pins",
     "login_url": "https://www.pinterest.com/login", "saved_url": "https://www.pinterest.com/{username}/_saved/",
     "domain": "pinterest.com", "auth_cookie": "_pinterest_sess", "extractor": "generic", "status": "experimental",
     "collector": "collect.py"},
]

BY_KEY = {p["key"]: p for p in PLATFORMS}

# Platforms whose saved_url needs the logged-in username resolved at runtime.
# (Reddit uses old.reddit.com/saved which auto-redirects, so no username needed.)
NEEDS_USERNAME = {"instagram", "tiktok", "pinterest"}
