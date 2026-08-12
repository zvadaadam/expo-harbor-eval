A booted iOS simulator has the GoldenNotes app installed (bundle id
`com.expo.simbench.goldennotes`). Create a note titled exactly
"Harbor Sim Bench 001" through the app's UI.

Use the simulator driver tool described in your run configuration to inspect
the screen and interact with the app. `bash driver/screenshot.sh out.png`
captures the simulator screen as a PNG if you need to look at pixels.

Rules: the note must be created through the app's UI. Do not write the app's
data files directly and do not inject state with `xcrun simctl` — the app
journals UI events, and a note without a matching UI event scores zero.
