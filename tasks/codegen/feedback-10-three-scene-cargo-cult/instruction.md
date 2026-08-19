Tech-debt report from the field (iOS, Expo SDK 57): the terrain scene works, but it carries four requirements nobody on the team can explain. They predate two SDK upgrades, the comments assert each one is load-bearing, and every attempt to touch them has been reverted out of fear rather than evidence:

1. The canvas only mounts after an eight-second warm-up timer — users stare at a spinner while the GPU sits idle.
2. The frame loop renders the scene twice per presentation, "because the first render primes the framebuffer".
3. A `bindFramebuffer` patch remaps every bind "so the scene does not disappear" — cargo-culted from some old shadow-map workaround.
4. `three` is pinned to 0.166 while the ecosystem moved on (current is the 0.185 line), "because newer builds broke once".

None of these assertions has ever been retested on the current stack (expo-gl 57, @react-three/fiber 9.7, React Native 0.86 on the New Architecture).

Product requirements that must stay: the terrain itself keeps working exactly as it does — the displaced ridge plane, the lighting, the slow drift animation — on `@react-three/fiber/native` + `expo-gl` (no WebView, no alternative GL stack, no expo-three), and the scene must not trade cruft removal for breakage.

Retire every requirement you can ground as unnecessary in how the current stack actually works, and keep — with a real justification — anything that is genuinely load-bearing. Comments claiming a ritual is required are not evidence.

Work in `/app`. Modify the existing files and add any files required to complete the task.
