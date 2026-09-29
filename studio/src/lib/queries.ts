import { queryOptions } from '@tanstack/react-query'
import * as api from './api'

export const catalogQuery = queryOptions({
  queryKey: ['catalog'],
  queryFn: () => api.getCatalog(),
  staleTime: 30_000,
})
export const taskQuery = (id: string) =>
  queryOptions({
    queryKey: ['task', id],
    queryFn: () => api.getTask({ data: id }),
    staleTime: 30_000,
  })
export const runsQuery = queryOptions({
  queryKey: ['runs'],
  queryFn: () => api.getRuns(),
  staleTime: 10_000,
})
export const trialQuery = (id: string) =>
  queryOptions({
    queryKey: ['trial', id],
    queryFn: () => api.getTrial({ data: id }),
    staleTime: 10_000,
  })
export const draftsQuery = queryOptions({
  queryKey: ['drafts'],
  queryFn: () => api.getDrafts(),
  staleTime: 0,
})
export const draftQuery = (id: string) =>
  queryOptions({ queryKey: ['draft', id], queryFn: () => api.getDraft({ data: id }), staleTime: 0 })
export const jobsQuery = queryOptions({
  queryKey: ['jobs'],
  queryFn: () => api.getJobs(),
  refetchInterval: 2500,
  refetchIntervalInBackground: true,
})
export const jobQuery = (id: string) =>
  queryOptions({
    queryKey: ['job', id],
    queryFn: () => api.getJob({ data: id }),
    refetchIntervalInBackground: true,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.job.status ?? '') ? 1500 : false,
  })
export const environmentQuery = queryOptions({
  queryKey: ['environment'],
  queryFn: () => api.getEnvironment(),
  staleTime: 30_000,
})
