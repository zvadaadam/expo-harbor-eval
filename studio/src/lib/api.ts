import { createServerFn } from '@tanstack/react-start'
import { z } from 'zod'
import {
  draftSchema,
  filePathSchema,
  jobPlanSchema,
  localIdSchema,
  modelPlanSchema,
  taskIdSchema,
} from './schema'

// Server-only imports stay inside compiler-extracted handlers.
export const getCatalog = createServerFn({ method: 'GET' }).handler(async () =>
  (await import('../server/repository.server')).catalog(),
)
export const getTask = createServerFn({ method: 'GET' })
  .validator(taskIdSchema)
  .handler(async ({ data }) => (await import('../server/repository.server')).task(data))
export const getTaskEdit = createServerFn({ method: 'GET' })
  .validator(taskIdSchema)
  .handler(async ({ data }) => (await import('../server/repository.server')).editTask(data))
export const updateTask = createServerFn({ method: 'POST' })
  .validator(
    z.object({
      task: taskIdSchema,
      fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
      draft: draftSchema,
    }),
  )
  .handler(async ({ data }) => {
    const server = await import('../server/repository.server')
    return server.action(() => server.updateTask(data))
  })
export const getRuns = createServerFn({ method: 'GET' }).handler(async () =>
  (await import('../server/repository.server')).runs(),
)
export const getTrial = createServerFn({ method: 'GET' })
  .validator(z.string().regex(/^[a-f0-9]{24}$/))
  .handler(async ({ data }) => (await import('../server/repository.server')).trial(data))
export const getTaskFile = createServerFn({ method: 'GET' })
  .validator(
    z.object({
      task: taskIdSchema,
      area: z.enum(['environment', 'reference', 'distractor', 'checks']),
      path: filePathSchema,
    }),
  )
  .handler(async ({ data }) =>
    (await import('../server/repository.server')).file({ ...data, action: 'task-file' }),
  )
export const getArtifact = createServerFn({ method: 'GET' })
  .validator(z.object({ id: z.string().regex(/^[a-f0-9]{24}$/), path: filePathSchema }))
  .handler(async ({ data }) =>
    (await import('../server/repository.server')).file({ ...data, action: 'artifact' }),
  )
export const getDrafts = createServerFn({ method: 'GET' }).handler(async () =>
  (await import('../server/repository.server')).store.listDrafts(),
)
export const getDraft = createServerFn({ method: 'GET' })
  .validator(localIdSchema)
  .handler(async ({ data }) => (await import('../server/repository.server')).store.readDraft(data))
export const saveDraft = createServerFn({ method: 'POST' })
  .validator(draftSchema)
  .handler(async ({ data }) => {
    const server = await import('../server/repository.server')
    return server.action(() => server.store.saveDraft(data))
  })
export const duplicateTask = createServerFn({ method: 'POST' })
  .validator(taskIdSchema)
  .handler(async ({ data }) => {
    const server = await import('../server/repository.server')
    return server.action(() => server.duplicate(data))
  })

export const getSimulatorTemplate = createServerFn({ method: 'GET' })
  .validator(taskIdSchema)
  .handler(async ({ data }) => {
    const server = await import('../server/repository.server')
    return server.action(() => server.simulatorTemplate(data))
  })
export const exportTask = createServerFn({ method: 'POST' })
  .validator(z.object({ id: localIdSchema, revision: z.number().int().positive() }))
  .handler(async ({ data }) => {
    const server = await import('../server/repository.server')
    return server.action(() => server.exportDraft(data.id, data.revision))
  })
export const getJobs = createServerFn({ method: 'GET' }).handler(async () =>
  (await import('../server/repository.server')).store.listJobs(),
)
export const getJob = createServerFn({ method: 'GET' })
  .validator(localIdSchema)
  .handler(async ({ data }) => (await import('../server/repository.server')).jobDetail(data))
export const launchJob = createServerFn({ method: 'POST' })
  .validator(jobPlanSchema)
  .handler(async ({ data }) => {
    const server = await import('../server/repository.server')
    return server.action(() => server.startJob(data))
  })
export const cancelJob = createServerFn({ method: 'POST' })
  .validator(localIdSchema)
  .handler(async ({ data }) => {
    const server = await import('../server/repository.server')
    return server.action(() => server.store.cancelJob(data))
  })
export const getModelPlan = createServerFn({ method: 'GET' })
  .validator(modelPlanSchema)
  .handler(async ({ data }) => (await import('../server/repository.server')).modelPlan(data))
export const getEnvironment = createServerFn({ method: 'GET' }).handler(async () =>
  (await import('../server/repository.server')).environment(),
)
export const getBlankDraft = createServerFn({ method: 'GET' }).handler(async () => {
  const { randomUUID } = await import('node:crypto')
  const { blankDraft } = await import('./editor-store')
  return blankDraft(randomUUID())
})

export function unwrap<T>(result: { ok: true; value: T } | { ok: false; message: string }): T {
  if (!result.ok) throw new Error(result.message)
  return result.value
}
