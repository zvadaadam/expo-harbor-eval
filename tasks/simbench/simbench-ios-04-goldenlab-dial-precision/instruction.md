A booted iOS simulator has the GoldenLab app installed (bundle id
`com.expo.simbench.goldenlab`). Open its **Dial** tab and save the
temperature at exactly **72**: adjust the dial to 72 and press "Save
temperature".

Use the simulator driver tool described in your run configuration to inspect
the screen and interact with the app. `bash driver/screenshot.sh out.png`
captures the simulator screen as a PNG if you need to look at pixels.

Rules: the value must be set and saved through the app's UI. Do not write the
app's data files directly and do not inject state with `xcrun simctl` — the
app journals UI events, and a saved value without a matching UI event scores
zero.
