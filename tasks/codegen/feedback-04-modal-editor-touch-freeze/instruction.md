Bug report from the field (iOS): adding the description editor to the post detail sheet freezes the app's touch input.

1. Open a post from the feed (it presents as a sheet) and tap "Edit description": the editor sheet never appears — visibly nothing happens.

2. Close the post sheet afterwards: the feed comes back but no longer responds to touches — every tap is dead until the app is force-quit.

We have tried two designs: presenting the editor as its own sheet on top of the post sheet, and a variant that dismissed the post sheet first and presented the editor after a short delay. Both ended in the frozen state (the delayed one intermittently, depending on how fast the first sheet finished dismissing). Toggling the modal flags after the freeze does not recover the app.

Product requirements that must stay: the post detail still presents modally over the feed, the description editor is reachable from the detail view, saving persists the new description (the feed card shows the updated copy), cancelling leaves the description unchanged, and closing everything returns to a fully interactive feed.

Rework the description editing flow so touch input always survives: opening the editor, saving, cancelling, and closing the detail must every time leave the app responsive.

Work in `/app`. Modify the existing files and add any files required to complete the task.
