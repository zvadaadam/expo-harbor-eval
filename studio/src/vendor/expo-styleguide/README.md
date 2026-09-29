# Expo website theme

`expo-theme.css` is vendored unchanged from **@expo/styleguide 14.4.0**, the
version used by `server/website` in the supplied Universe checkout. It imports
the published `@radix-ui/colors` palettes. The matching Expo wordmark path is
in `src/components/expo-logo.tsx`. Both are covered by the accompanying MIT
license.

Source: https://www.npmjs.com/package/@expo/styleguide/v/14.4.0

The published styleguide's component package has a Next.js peer dependency.
Vendoring its framework-independent theme lets this TanStack Start app use the
actual website tokens without adding a second application framework. Its theme
differs from the older JavaScript colors exported by `@expo/styleguide-base`.

Layout and control sizing follow the supplied website's `Sidebar.tsx`,
`SidebarNavigation`, `PageHeader.tsx`, `ButtonInternal.tsx`, `form/Input.tsx`,
`Breadcrumbs`, and dashboard project tiles. Navigation and application state
remain owned by TanStack Router, Query, and Zustand.
