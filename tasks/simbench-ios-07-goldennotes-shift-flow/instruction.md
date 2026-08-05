A booted iOS simulator has the GoldenNotes app installed (bundle id
`com.expo.simbench.goldennotes`). Complete an opening-shift flow through the
app's UI, in this exact order:

1. In Notes, create a note titled exactly "Shift Opened 007".
2. In Inventory, claim "Item 019".
3. In Inventory, claim "Item 052".
4. In Register, submit full name "Riley Chen" with access code "DOCK-7".

Use the simulator driver tool described in your run configuration to inspect
the screen and interact with the app. `bash driver/screenshot.sh out.png`
captures the simulator screen as a PNG if you need to look at pixels.

Rules: every step must go through the app's UI, in the order above. The app
journals UI events, and the verifier requires the journal to show these four
steps in sequence — state without matching journal events, or steps out of
order, scores zero. Do not write the app's data files directly and do not
inject state with `xcrun simctl`.
