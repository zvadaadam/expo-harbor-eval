import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useQuery, useSuspenseQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { runsQuery, jobsQuery } from '../lib/queries'
import { Badge, Button, Metric, Notice, PageHeader, Status } from '../components/ui'
import { PlayIcon, RefreshIcon, SearchIcon, ArrowRightIcon } from '../components/icons'
import { TrialTable } from '../components/trial-table'

export const Route = createFileRoute('/runs')({
  validateSearch: z.object({
    q: z.string().catch('').default(''),
    outcome: z.string().catch('all').default('all'),
  }),
  loader: ({ context }) => context.queryClient.ensureQueryData(runsQuery),
  component: Runs,
})
function Runs() {
  const result = useSuspenseQuery(runsQuery)
  const jobs = useQuery(jobsQuery)
  const { q, outcome } = Route.useSearch()
  const navigate = useNavigate({ from: '/runs' })
  const trials = result.data.trials
  const filtered = trials.filter(
    (t) =>
      (outcome === 'all' || t.outcome === outcome) &&
      `${t.task} ${t.run} ${t.model}`.toLowerCase().includes(q.toLowerCase()),
  )
  return (
    <>
      <PageHeader
        title="Runs"
        description="Every attempt, its outcome, and the evidence behind it."
        actions={
          <>
            <Button busy={result.isFetching} onClick={() => void result.refetch()}>
              <RefreshIcon />
              Refresh
            </Button>
            <Link to="/run" className="button primary">
              <PlayIcon />
              New run
            </Link>
          </>
        }
      />
      <div className="metrics">
        <Metric value={new Set(trials.map((t) => t.run)).size} label="Saved run groups" />
        <Metric value={trials.filter((t) => !t.regradeOf).length} label="Original attempts" />
        <Metric value={trials.filter((t) => !!t.regradeOf).length} label="Saved-answer regrades" />
        <Metric
          value={trials.filter((t) => ['error', 'pending'].includes(t.outcome)).length}
          label="Errors / missing results"
        />
      </div>
      {result.data.warnings.map((w) => (
        <Notice key={w} tone="warning">
          {w}
        </Notice>
      ))}
      {!!jobs.data?.length && (
        <section className="recent-jobs">
          <div className="section-heading">
            <h2>Local controls</h2>
            <Badge>No model calls</Badge>
          </div>
          {jobs.data.slice(0, 5).map((job) => (
            <Link key={job.id} className="job-row" to="/jobs/$jobId" params={{ jobId: job.id }}>
              <span className="job-dot">
                <PlayIcon />
              </span>
              <div>
                <strong>{job.task}</strong>
                <small>
                  {job.action === 'harbor'
                    ? 'Harbor reference smoke'
                    : job.action === 'policy'
                      ? 'Policy calibration'
                      : 'Guard calibration'}
                </small>
              </div>
              <Status status={job.status} />
              <ArrowRightIcon />
            </Link>
          ))}
        </section>
      )}
      <div className="library-toolbar">
        <div className="search-field">
          <SearchIcon />
          <input
            aria-label="Search runs"
            placeholder="Search by task, run group, or model…"
            value={q}
            onChange={(e) =>
              void navigate({
                search: { q: e.target.value, outcome },
                replace: true,
                resetScroll: false,
              })
            }
          />
        </div>
        <select
          aria-label="Filter by outcome"
          value={outcome}
          onChange={(e) =>
            void navigate({
              search: { q, outcome: e.target.value },
              replace: true,
              resetScroll: false,
            })
          }
        >
          <option value="all">All outcomes</option>
          <option value="pass">Passed</option>
          <option value="fail">Failed</option>
          <option value="partial">Partial</option>
          <option value="error">Execution error</option>
          <option value="pending">Missing result</option>
        </select>
      </div>
      <TrialTable trials={filtered} />
    </>
  )
}
