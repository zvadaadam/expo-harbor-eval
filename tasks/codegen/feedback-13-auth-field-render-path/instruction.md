The sign-in and create-account screens in this Expo iOS app have text fields that are taller than their native submit buttons. Earlier changes to a reusable text-field component did not affect either authentication screen.

Make the outer height of every visible authentication field exactly 52 points at the default text size, matching the existing submit button. Keep the content vertically centered and retain the 14-point horizontal content inset. Use the existing Expo UI SwiftUI inputs and secure password input.

Preserve both authentication modes, editable email/password state, masked password entry, and the submit confirmation using the current values. The Settings screen intentionally uses a compact 44-point profile-name field; leave that behavior intact. Keep route switching and all current labels.

Do not resize the button to match the broken fields, hide or clip content to conceal excess height, replace native controls with DOM elements, or remove a route. A min-height that can expand is insufficient for this fixed-height product contract at standard text size. Dynamic Type beyond the default size is outside this fixture's scope.

The files are reconstructed from a reported failure rather than copied from the original app. Find and repair the implementation that these screens actually render.
