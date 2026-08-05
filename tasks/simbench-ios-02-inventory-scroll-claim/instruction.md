A booted iOS simulator has the GoldenNotes app installed (bundle id
`com.expo.simbench.goldennotes`). Open its **Inventory** tab — a list of 60
items — and claim the item named exactly "Item 047" by pressing the Claim
button on that item's row.

The target row starts far below the visible area, so you will need to scroll
the list to reach it. Use the simulator driver tool described in your run
configuration to inspect the screen and interact with the app.
`bash driver/screenshot.sh out.png` captures the simulator screen as a PNG if
you need to look at pixels.

Rules: the claim must be made through the app's UI. Do not write the app's
data files directly and do not inject state with `xcrun simctl` — the app
journals UI events, and a claim without a matching UI event scores zero.
