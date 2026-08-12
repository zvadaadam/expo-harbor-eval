A booted iOS simulator has the GoldenNotes app installed (bundle id
`com.expo.simbench.goldennotes`). Open its **Register** tab and register with
full name "Ada Lovelace" and access code "EXPO-7431": fill both fields with
exactly those values, then press the Register button.

Beware: the Register button is pinned to the bottom of the screen and the
screen does not move it out of the keyboard's way. Use the simulator driver
tool described in your run configuration to inspect the screen and interact
with the app. `bash driver/screenshot.sh out.png` captures the simulator
screen as a PNG if you need to look at pixels.

Rules: the registration must be submitted through the app's UI, and the two
field values must match exactly. Do not write the app's data files directly
and do not inject state with `xcrun simctl` — the app journals UI events, and
a registration without a matching UI event scores zero.
