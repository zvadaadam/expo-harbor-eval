Bug report from the field: on a cold launch, the Sessions list renders behind the status bar and Dynamic Island — the first rows start at the very top of the screen, underneath the transparent large-title header. After any re-layout (for example a Fast Refresh during development) the spacing corrects itself, so the bug only shows on the first launch of a fresh install, which is why it reaches real users.

The transparent header, large title, and header search bar are product requirements and must stay. Fix the Sessions screen so the list content is correctly inset below the header from the very first render, on both iOS and Android.

Work in `/app`. Modify the existing files and add any files required to complete the task.
