Bug report from the field, reproduced on iPhone hardware and the iOS simulator: the exposure trim knob in the photo editor is a *relative* control — every drag is supposed to nudge the running EV total by the released offset, and the knob is supposed to snap back to the middle the moment you let go. On iOS the knob never snaps back.

1. Drag the knob anywhere and release: the running EV total updates, but the knob stays where you dropped it. The next drag then starts from the stale position and reads as the wrong nudge.

2. Release the knob at either end and it is stuck there for good — no later release brings it back to the middle.

We already tried snapping it back by setting the slider's value to 0 — the centre of our −1…+1 range — on release, and in a second attempt by also force-remounting the Slider with a changed key after each release; on iOS the thumb still did not move back either way. The installed wrapper is vendored under `node_modules/@react-native-community/slider/` (trimmed to the file that matters) if you need to check what the component actually does with the props it is given.

Product requirements that must stay: the control remains `@react-native-community/slider` at the pinned 5.0.1 (dependency changes and edits under `node_modules/` do not ship this sprint), each completed drag still adds its released offset — scaled so a full centre-to-end drag is 0.50 EV — to the running total, repeated nudges can push the total past ±0.50 EV, releasing at the centre changes nothing, and the knob visibly returns to the centre after every release, including releases at the ends.

Fix the exposure trimmer so the knob reliably recenters on iOS while the relative accumulation keeps working.

Work in `/app`. Modify the existing files and add any files required to complete the task.
