Repair the summary row in this Expo SDK 57 app. At 360dp on Android (font scale 1.0), the amount column is not readable even though the web layout looked correct.

Requirements:
- At viewport widths 320, 360, 390 and 430dp, keep the description, a 112dp amount column, and the 24dp visibility control inside the row. Keep 16dp screen insets and 12dp gaps.
- The description takes the remaining space and may truncate to one line. The amount label and formatted value must each stay on one line within their column at font scale 1.0; keep their current text and font sizes.
- The visibility control must still toggle the amount between its formatted value and the supplied mask. Preserve its accessible label and press behavior.
- Keep the two-column summary and adjacent control, including narrow Android screens. Do not hide/remove content, shrink text, hard-code a viewport width, use absolute positioning, clip the overflow to conceal it, or replace the screen with a web view.

The app includes short and long description fixtures. Repair the code that actually renders the summary; a web-only change is insufficient. These are reconstructed fixtures inspired by a field report, not the original application.
