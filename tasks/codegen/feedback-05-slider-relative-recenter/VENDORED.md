# Vendored wrapper provenance

`environment/node_modules/@react-native-community/slider/` is a trimmed,
byte-identical excerpt of the published npm artifact, vendored so the task
can exercise reading the installed wrapper source. Do not edit or upgrade
these files — the rubric's ground truth is pinned to them. This note lives
at the task root (not inside `environment/`) so solving agents never see it.

- Upstream: `@react-native-community/slider` 5.0.1 (MIT, Callstack);
  registry tarball published 2025-08-19, `dist.shasum`
  `478789e526af31e0660c6f49fa5c5429d8d4287b`
- `sha256(package.json)` =
  `df404cc16972a1de31f90d25befdc3a1157cdc844be48632f29b842ccd3bf578`
- `sha256(dist/Slider.js)` =
  `ea96eef18ecb5b0c37799936e586a00ecc29813f0543538e04621f0528db642d`
- `tests/test_task_authoring.py` asserts the wrapper stays present and keeps
  the load-bearing falsy-value coercion.
