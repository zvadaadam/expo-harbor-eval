import { createCsrfMiddleware, createMiddleware, createStart } from '@tanstack/react-start'

const localOnly = createMiddleware().server(({ request, next }) => {
  const hostname = new URL(request.url).hostname
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(hostname))
    return new Response('Studio is only available on loopback.', { status: 403 })
  return next()
})

export const startInstance = createStart(() => ({
  requestMiddleware: [
    localOnly,
    createCsrfMiddleware({ filter: (context) => context.handlerType === 'serverFn' }),
  ],
}))
