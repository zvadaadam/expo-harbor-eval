Bug report from the field: invitation links break for anyone who doesn't land in the app.

1. Invites are shared as `https://emberline.app/invite/<code>`. With the app installed and link verification active, tapping one opens the invite screen natively — that part works on both platforms.

2. For everyone else the same link is a 404: friends without the app, desktop browsers, iOS users who once picked "open in browser" for our domain, links tapped inside Instagram-style in-app browsers, the URL typed straight into an address bar, and Android devices where our link verification is off. Link previews in messaging apps show nothing useful either.

The association side is done: `.well-known/apple-app-site-association` and `.well-known/assetlinks.json` are served from the web build and both platforms verify. We already tried tightening and widening the link patterns on both platforms — it changed nothing about the browser cases, which still 404.

Product requirements that must stay: invites keep being shared as the one canonical HTTPS URL (no switching shares to `emberline://` links or a second domain), native interception keeps working exactly as it does today (the association config and files stay valid), and the canonical URL must now land somewhere usable in every non-app case — a page that shows what the invite is, offers to open it in the app with the code intact, and points to the App Store / Play Store when the app isn't there.

Make the canonical invite URL work everywhere.

Work in `/app`. Modify the existing files and add any files required to complete the task.
