Bug report from the field, on Android hardware (the app runs edge-to-edge, which is the SDK 56 default and must stay): the "New verse" popup is unusable while typing.

1. Tap the verse input: the keyboard opens but the popup does not shrink — the Save and Cancel buttons sit hidden behind the keyboard the whole time you type.

2. We already padded the composer's scroll area so the input can be scrolled back into view. The input is visible now, but the buttons are still behind the keyboard: to save a verse you must dismiss the keyboard first, and testers keep losing drafts by hitting back instead.

iOS already behaves acceptably and must keep working.

Product requirements that must stay: the popup remains a transparent modal floating over the dimmed reading screen, the verse input stays multiline and scrollable for long verses, Save and Cancel stay visible and tappable the whole time the keyboard is open (a tap must register on the first try), the popup returns to its normal size when the keyboard hides, and Android back still closes the popup.

Fix the popup so its viewport resizes above the keyboard instead of hiding the actions.

Work in `/app`. Modify the existing files and add any files required to complete the task.
