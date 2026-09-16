A booted iOS simulator has the GoldenGate app installed (bundle id
`com.expo.simbench.goldengate`). GoldenGate signs in against an identity
provider called **HarborID**.

On the **Account** tab, choose **Sign in inside the app** to open the HarborID
sign-in page inside the app, then sign in with:

- Username: `ada.lovelace`
- Access code: `engine-1843`

When HarborID asks whether to allow GoldenGate to access your account, allow it.
A successful sign-in returns to the Account screen showing "Signed in as Ada
Lovelace".

Use the simulator driver tool described in your run configuration to inspect
the screen and interact with the app. `bash driver/screenshot.sh out.png`
captures the simulator screen as a PNG if you need to look at pixels.

Rules: the whole sign-in must happen through the app's UI, including the
HarborID login and the access-consent step. Do not write the app's data files
directly and do not inject state with `xcrun simctl` — the app and the
provider journal every step, and a session that did not come out of the
HarborID login and consent pages scores zero.
