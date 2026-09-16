A booted iOS simulator has the GoldenGate app installed (bundle id
`com.expo.simbench.goldengate`). GoldenGate signs in against an identity
provider called **HarborID**.

On the **Account** tab, choose **Sign in with Safari**. GoldenGate hands off to
the Safari browser to complete the HarborID login. Sign in there with:

- Username: `grace.hopper`
- Access code: `cobol-1959`

Allow GoldenGate to access your account when HarborID asks. HarborID then
returns to GoldenGate through its `goldengate://` link; if Safari asks whether
to open the page in GoldenGate, confirm it. Back on the Account screen,
GoldenGate shows "Signed in as Grace Hopper".

Use the simulator driver tool described in your run configuration to inspect
the screen and interact with the app. `bash driver/screenshot.sh out.png`
captures the simulator screen as a PNG if you need to look at pixels.

Rules: the whole sign-in must happen through the UI — the Safari login, the
access-consent step and the return hand-off into GoldenGate. Do not write the
app's data files directly and do not inject state with `xcrun simctl` — the app
and the provider journal every step, and a session that did not come out of the
HarborID login and consent pages scores zero.
