import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { z } from 'zod'
import { catalogQuery } from '../lib/queries'
import { getModelPlan, launchJob, unwrap } from '../lib/api'
import type { JobPlan } from '../lib/schema'
import { BackLink, Badge, Button, download, Notice, PageHeader } from '../components/ui'
import {
  CheckCircleIcon,
  DownloadIcon,
  PlayIcon,
  ShieldIcon,
  TerminalIcon,
} from '../components/icons'

export const Route = createFileRoute('/run')({
  validateSearch: z.object({ task: z.string().catch('').default('') }),
  loader: ({ context }) => context.queryClient.ensureQueryData(catalogQuery),
  component: RunSetup,
})
function RunSetup() {
  const catalog = useSuspenseQuery(catalogQuery).data
  const search = Route.useSearch()
  const [taskId, setTaskId] = useState(
    search.task ||
      catalog.tasks.find((t) => t.measurements.includes('policy-behavior'))?.id ||
      catalog.tasks[0]?.id ||
      '',
  )
  const [action, setAction] = useState<JobPlan['action']>('guards')
  const [effort, setEffort] = useState<'low' | 'medium' | 'high'>('low')
  const [attempts, setAttempts] = useState(1)
  const task = catalog.tasks.find((t) => t.id === taskId)
  const navigate = useNavigate()
  const client = useQueryClient()
  const launch = useMutation({
    mutationFn: async () => unwrap(await launchJob({ data: { task: taskId, action } })),
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ['jobs'] })
      void navigate({ to: '/jobs/$jobId', params: { jobId: job.id } })
    },
  })
  const plan = useMutation({
    mutationFn: () => getModelPlan({ data: { task: taskId, effort, attempts } }),
    onSuccess: (value) => download(value.filename, value.content),
  })
  const canRun = task && !task.held && task.family === 'expo-codegen'
  const options: {
    id: JobPlan['action']
    title: string
    description: string
    disabled?: boolean
  }[] = [
    {
      id: 'guards',
      title: 'Check the guardrails',
      description: 'Empty and unchanged submissions must score zero. No judge calls.',
    },
    {
      id: 'policy',
      title: 'Calibrate the policy contract',
      description: 'Run good and bad controls against the executable JavaScript contract.',
      disabled: !task?.measurements.includes('policy-behavior'),
    },
    {
      id: 'harbor',
      title: 'Run a Harbor smoke test',
      description: 'Run no-op and reference agents through Harbor. Exact reference checks only.',
    },
  ]
  return (
    <>
      <BackLink />
      <PageHeader
        title="Set up a run"
        description="Start with a local control. Know exactly what runs before you launch."
      />
      <div className="setup-layout">
        <div>
          <section className="panel form-section">
            <div className="step-heading">
              <span>01</span>
              <h2>Choose a task</h2>
            </div>
            <label htmlFor="run-task">Task</label>
            <select
              id="run-task"
              value={taskId}
              onChange={(e) => {
                setTaskId(e.target.value)
                setAction('guards')
              }}
            >
              {catalog.tasks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                  {t.held ? ' (on hold)' : ''}
                </option>
              ))}
            </select>
            <p className="field-hint">{task?.description}</p>
            {!canRun && (
              <Notice tone="warning">
                {task?.held
                  ? 'This task is held pending driver support. Execution is unavailable.'
                  : 'Simulator task controls use the repository CLI. This first Studio release launches coding controls.'}
              </Notice>
            )}
          </section>
          <section className="panel form-section">
            <div className="step-heading">
              <span>02</span>
              <h2>Choose a local control</h2>
            </div>
            <div className="radio-cards">
              {options.map((option) => (
                <label
                  key={option.id}
                  className={`radio-card ${action === option.id ? 'selected' : ''} ${option.disabled ? 'disabled' : ''}`}
                >
                  <input
                    type="radio"
                    name="action"
                    value={option.id}
                    checked={action === option.id}
                    disabled={option.disabled || !canRun}
                    onChange={() => setAction(option.id)}
                  />
                  <div>
                    <strong>{option.title}</strong>
                    <p>{option.description}</p>
                    {option.disabled && <small>Requires an executable policy contract</small>}
                  </div>
                </label>
              ))}
            </div>
          </section>
          <section className="panel form-section model-planner">
            <div className="step-heading">
              <TerminalIcon />
              <h2>Plan a Sonnet experiment</h2>
              <Badge>CLI export</Badge>
            </div>
            <p>
              Use your logged-in Claude CLI. Generation and judging consume usage. This plan has no
              enforced dollar cap, so paid launches stay an explicit terminal action.
            </p>
            <div className="form-grid">
              <label>
                Reasoning effort
                <select value={effort} onChange={(e) => setEffort(e.target.value as typeof effort)}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label>
                Attempts
                <select value={attempts} onChange={(e) => setAttempts(Number(e.target.value))}>
                  {[1, 2, 3].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="field-hint">
              {attempts} candidate {attempts === 1 ? 'attempt' : 'attempts'} + up to {attempts}{' '}
              judge {attempts === 1 ? 'execution' : 'executions'}. Change only effort when comparing
              reasoning.
            </p>
            <Button busy={plan.isPending} disabled={!canRun} onClick={() => plan.mutate()}>
              <DownloadIcon />
              Download Harbor plan
            </Button>
            {plan.error && <Notice tone="error">{plan.error.message}</Notice>}
            {plan.isSuccess && (
              <Notice tone="success">
                Plan downloaded. From the repository root:{' '}
                <code>
                  uv run harbor run -c /path/to/{plan.data.filename} --job-name your-unique-run-name
                  --yes
                </code>
                . Use a new job name for each experiment.
              </Notice>
            )}
          </section>
        </div>
        <aside>
          <section className="panel run-summary">
            <span className="feature-icon">
              <ShieldIcon />
            </span>
            <h2>Your local run</h2>
            <Badge tone="green">No model usage</Badge>
            <dl className="detail-list">
              <div>
                <dt>Scope</dt>
                <dd>1 coding task</dd>
              </div>
              <div>
                <dt>Action</dt>
                <dd>
                  {action === 'harbor'
                    ? 'Reference smoke'
                    : action === 'policy'
                      ? 'Policy calibration'
                      : 'Guard calibration'}
                </dd>
              </div>
              <div>
                <dt>Concurrency</dt>
                <dd>1 local job</dd>
              </div>
              <div>
                <dt>Time limit</dt>
                <dd>10 minutes</dd>
              </div>
              <div>
                <dt>Model / judge calls</dt>
                <dd>0</dd>
              </div>
            </dl>
            <p className="small-note">
              <CheckCircleIcon />
              Original results are preserved. Controls write a new local job.
            </p>
            <Button
              variant="primary"
              busy={launch.isPending}
              disabled={!canRun}
              onClick={() => launch.mutate()}
            >
              <PlayIcon />
              Run local control
            </Button>
            {launch.error && <Notice tone="error">{launch.error.message}</Notice>}
          </section>
          <p className="aside-note">
            A smoke test checks the harness. Guard checks and policy contracts each cover only their
            stated scope; full judge calibration is separate.
          </p>
        </aside>
      </div>
    </>
  )
}
