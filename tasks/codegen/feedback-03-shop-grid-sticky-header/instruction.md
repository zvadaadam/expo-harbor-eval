Bug report from the field, reproduced on a physical iPhone: the Shop tab's product grid is broken in two ways.

1. The first row of cards is stretched to fill most of the screen, and each card cuts off its product copy — the full copy never becomes readable no matter how far you scroll.

2. The condensed "Shop" bar that fades in after you scroll past the hero gets stuck. Repro: scroll the grid down until the bar is fully visible, switch to the Home tab, then return to Shop. The screen comes back at the top of the grid — offset zero — but the bar is still showing.

Product requirements that must stay: the bottom tabs keep freezeOnBlur (a performance decision), the condensed bar still fades in once the hero scrolls away, and returning to the Shop tab still lands at the top of the grid.

Fix the Shop screen so every card sizes to its content with the full copy laid out, and the condensed bar is visible exactly when the current scroll position is past the hero — including after any number of tab switches.

Work in `/app`. Modify the existing files and add any files required to complete the task.
