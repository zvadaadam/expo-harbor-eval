A booted iOS simulator has the GoldenLab app installed (bundle id
`com.expo.simbench.goldenlab`). Open its **Grid** tab — a 5x5 grid of
colored squares — and tap the single **red** square. Tapping more than 3
non-red squares fails the task.

The squares do not appear in the accessibility tree, so you will need to look
at the screen. `bash driver/screenshot.sh out.png` captures the simulator
screen as a PNG. Use the simulator driver tool described in your run
configuration to interact with the app.

Rules: the tap must go through the app's UI. Do not write the app's data
files directly and do not inject state with `xcrun simctl` — the app journals
UI events, and a tap without a matching UI event scores zero.
