import {
  createRootRouteWithContext,
  HeadContent,
  Link,
  Outlet,
  Scripts,
} from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { Shell } from '../components/shell'
import { themeVariables } from '../lib/theme'
import { Notice } from '../components/ui'
import stylesheet from '../styles.css?url'

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Expo Evals · Harbor Studio' },
    ],
    links: [{ rel: 'stylesheet', href: stylesheet }],
  }),
  shellComponent: Document,
  component: () => (
    <Shell>
      <Outlet />
    </Shell>
  ),
  notFoundComponent: () => (
    <div className="empty">
      <h1>Page not found</h1>
      <Link to="/" className="button primary">
        Open the task library
      </Link>
    </div>
  ),
  errorComponent: ({ error, reset }) => (
    <div className="error-page">
      <h1>Couldn’t load this view</h1>
      <Notice tone="error">
        {error instanceof Error ? error.message : 'The local reader could not load this page.'}
      </Notice>
      <button className="button secondary" onClick={reset}>
        Try again
      </button>
      <Link to="/">Back to library</Link>
    </div>
  ),
})
function Document({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" style={themeVariables as React.CSSProperties}>
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  )
}
