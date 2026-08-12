A booted iOS simulator has the GoldenLab app installed (bundle id
`com.expo.simbench.goldenlab`). Open its **Reveal** tab, reveal the access
code, and submit exactly that code through the entry field.

Use the simulator driver tool described in your run configuration to inspect
the screen and interact with the app. `bash driver/screenshot.sh out.png`
captures the simulator screen as a PNG if you need to look at pixels.

Rules: the code must be revealed, read, and submitted through the app's UI.
Do not write the app's data files directly and do not inject state with
`xcrun simctl` — the app journals UI events, and a submission without the
matching UI events scores zero.
