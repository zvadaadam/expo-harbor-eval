A booted iOS simulator has the GoldenGate app installed (bundle id
`com.expo.simbench.goldengate`). GoldenGate signs in against an identity
provider called **HarborID** using the system sign-in sheet (the same
`ASWebAuthenticationSession` flow Expo apps use through `expo-web-browser` /
`expo-auth-session`).

On the **Account** tab, choose **Continue with HarborID**. iOS first shows a
"'GoldenGate' Wants to Use '127.0.0.1' to Sign In" confirmation — accept it to
open the HarborID sheet. Then sign in with:

- Username: `riley.chen`
- Access code: `harbor-2026`

When HarborID asks whether to allow GoldenGate to access your account, allow it.
The sheet closes by itself and the Account screen shows "Signed in as Riley
Chen".

Use the simulator driver tool described in your run configuration to inspect
the screen and interact with the app. `bash driver/screenshot.sh out.png`
captures the simulator screen as a PNG if you need to look at pixels.

Rules: the whole sign-in must happen through the app's UI, including the iOS
confirmation, the HarborID login and the access-consent step. Do not write the
app's data files directly and do not inject state with `xcrun simctl` — the app
and the provider journal every step, and a session that did not come out of the
HarborID login and consent pages scores zero.
