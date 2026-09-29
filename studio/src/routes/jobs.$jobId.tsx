import { createFileRoute, Link } from '@tanstack/react-router'
import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query'
import { jobQuery } from '../lib/queries'
import { cancelJob, unwrap } from '../lib/api'
import { Badge, Button, Notice, PageHeader, Status } from '../components/ui'
import { ArrowLeftIcon, RefreshIcon, TerminalIcon } from '../components/icons'

export const Route = createFileRoute('/jobs/$jobId')({
  loader: ({ params, context }) => context.queryClient.ensureQueryData(jobQuery(params.jobId)),
  component: JobPage,
})
function JobPage() {
  const { jobId } = Route.useParams()
  const { data, refetch, isFetching, error } = useSuspenseQuery(jobQuery(jobId))
  const client = useQueryClient()
  const cancel = useMutation({
    mutationFn: async () => unwrap(await cancelJob({ data: jobId })),
    onSuccess: () => client.invalidateQueries({ queryKey: ['job', jobId] }),
  })
  const active = ['running', 'queued'].includes(data.job.status)
  return (
    <>
      <Link to="/runs" className="back-link">
        <ArrowLeftIcon />
        All runs
      </Link>
      <PageHeader
        title={
          data.job.action === 'harbor'
            ? 'Harbor reference smoke'
            : data.job.action === 'policy'
              ? 'Policy calibration'
              : 'Guard calibration'
        }
        description={data.job.task}
        actions={
          <>
            <Status status={data.job.status} />
            <Button busy={isFetching} onClick={() => void refetch()}>
              <RefreshIcon />
              Refresh
            </Button>
            {active && (
              <Button
                variant="danger"
                busy={cancel.isPending}
                disabled={cancel.isSuccess}
                onClick={() => cancel.mutate()}
              >
                {cancel.isSuccess ? 'Stopping…' : 'Cancel run'}
              </Button>
            )}
          </>
        }
      />
      <div className="task-meta">
        <Badge tone="green">No model calls</Badge>
        <code>{jobId}</code>
      </div>
      {data.job.message && (
        <Notice tone={data.job.status === 'failed' ? 'error' : 'info'}>{data.job.message}</Notice>
      )}
      {cancel.error && <Notice tone="error">{cancel.error.message}</Notice>}
      {error && (
        <Notice tone="error">
          Live updates stopped: {error.message}. Use Refresh to reconnect.
        </Notice>
      )}
      <section className="job-log">
        <div className="file-bar">
          <TerminalIcon />
          Execution log <Badge>{active ? 'Updates automatically' : 'Saved locally'}</Badge>
        </div>
        <pre className="code-preview" tabIndex={0}>
          {data.log ||
            (data.job.status === 'queued'
              ? 'Waiting for the local execution slot…'
              : 'Waiting for process output…')}
        </pre>
      </section>
      <div className="actions below-log">
        <Link to="/tasks/$taskId" params={{ taskId: data.job.task }} className="button secondary">
          Back to task
        </Link>
        {data.job.action === 'harbor' && !active && (
          <Link
            to="/runs"
            search={{ q: `studio-${jobId}`, outcome: 'all' }}
            className="button primary"
          >
            Inspect Harbor attempts
          </Link>
        )}
      </div>
    </>
  )
}
