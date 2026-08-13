Bug report from the field, seen on device and simulator: reordering photos on the moodboard by long-pressing and dragging is visually broken.

1. While a photo is being dragged, the other tiles flash and stutter as they make room — on fast drags some tiles blink, and interrupted shuffles restart from the wrong place.

2. The dragged photo itself jumps under the finger every time it crosses into a new slot, then keeps fighting the finger for the rest of the drag.

We shipped two attempts that kept re-sorting the photo array as the drag crossed each slot boundary and let the grid's layout animation move everything into place; tuning the transition and the keys did not stop the flashing or the under-finger jumps.

Product requirements that must stay: picking up a photo still requires a long press, the grid stays 3 columns with every photo visible, the displaced tiles glide out of the way while the drag is in progress (no teleporting), and letting go saves the new order.

Rework the drag-to-reorder so the dragged photo tracks the finger continuously and the other tiles animate smoothly, with no flashing, blinking, or under-finger jumps.

Work in `/app`. Modify the existing files and add any files required to complete the task.
