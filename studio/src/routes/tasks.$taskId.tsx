import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { z } from 'zod'
import { taskQuery, runsQuery } from '../lib/queries'
import { duplicateTask, getTaskFile, unwrap } from '../lib/api'
import {
  BackLink,
  Badge,
  Button,
  categoryNames,
  measurementNames,
  Notice,
  PageHeader,
  readiness,
} from '../components/ui'
import {
  CopyIcon,
  FileIcon,
  PlayIcon,
  ShieldIcon,
  CheckCircleIcon,
  CodeIcon,
} from '../components/icons'
import { FilePreview } from '../components/file-preview'
import { TrialTable } from '../components/trial-table'
import type { TaskDetail } from '../lib/schema'
import { graders } from '../lib/grading'

export const Route = createFileRoute('/tasks/$taskId')({
  validateSearch: z.object({
    tab: z.enum(['overview', 'checks', 'files', 'attempts']).catch('overview').default('overview'),
  }),
  loader: ({ params, context }) =>
    Promise.all([
      context.queryClient.ensureQueryData(taskQuery(params.taskId)),
      context.queryClient.ensureQueryData(runsQuery),
    ]),
  component: TaskPage,
})
function TaskPage() {
  const { taskId } = Route.useParams()
  const { tab } = Route.useSearch()
  const { data: task } = useSuspenseQuery(taskQuery(taskId))
  const { data: runs } = useSuspenseQuery(runsQuery)
  const trials = runs.trials.filter((t) => t.task === task.id)
  const navigate = useNavigate()
  const client = useQueryClient()
  const duplicate = useMutation({
    mutationFn: async () => unwrap(await duplicateTask({ data: task.id })),
    onSuccess: (draft) => {
      void client.invalidateQueries({ queryKey: ['drafts'] })
      void navigate({ to: '/drafts/$draftId', params: { draftId: draft.id } })
    },
  })
  return (
    <>
      <BackLink />
      <PageHeader
        eyebrow={categoryNames[task.category]}
        title={task.title}
        description={task.description}
        actions={
          <>
            <Link to="/tasks/$taskId/edit" params={{ taskId }} className="button secondary">
              Edit task
            </Link>
            <Button busy={duplicate.isPending} onClick={() => duplicate.mutate()}>
              <CopyIcon />
              Duplicate
            </Button>
            <Link to="/run" search={{ task: task.id }} className="button primary">
              <PlayIcon />
              Run task
            </Link>
          </>
        }
      />
      {duplicate.error && <Notice tone="error">{duplicate.error.message}</Notice>}
      <div className="task-meta">
        <Badge>{task.difficulty} difficulty</Badge>
        {task.measurements.map((m) => (
          <Badge tone={m === 'native-ui' ? 'purple' : 'blue'} key={m}>
            {measurementNames[m]}
            {m === 'native-ui' ? ' · experimental' : ''}
          </Badge>
        ))}
        <code>{task.id}</code>
      </div>
      <div className="page-tabs">
        {(['overview', 'checks', 'files', 'attempts'] as const).map((name) => (
          <Link
            key={name}
            to="/tasks/$taskId"
            params={{ taskId }}
            search={{ tab: name }}
            className={tab === name ? 'selected' : ''}
            resetScroll={false}
          >
            {name[0].toUpperCase() + name.slice(1)}
            {name === 'checks' && task.checks > 0 && <span>{task.checks}</span>}
            {name === 'attempts' && <span>{trials.length}</span>}
          </Link>
        ))}
      </div>
      {tab === 'overview' && (
        <div className="detail-columns">
          <div>
            <section className="panel">
              <div className="panel-heading">
                <CodeIcon />
                <h2>The agent’s brief</h2>
                <Badge>instruction.md</Badge>
              </div>
              <div className="markdown">
                <ReactMarkdown>{task.instruction}</ReactMarkdown>
              </div>
            </section>
            <section className="panel motivation">
              <h2>Why this task exists</h2>
              <p>{task.motivation || 'No motivation recorded in task metadata.'}</p>
            </section>
          </div>
          <aside>
            <section className="panel readiness-panel">
              <span className="feature-icon">
                <ShieldIcon />
              </span>
              <h2>Calibration</h2>
              <Badge tone={task.held ? 'amber' : 'neutral'} dot>
                {readiness(task.validation)}
              </Badge>
              <p>
                {task.validationNote ||
                  'This definition has no recorded calibration status. A reference solution alone does not establish a trustworthy grader.'}
              </p>
              <dl className="detail-list">
                <div>
                  <dt>Reference control</dt>
                  <dd>{task.hasReference ? 'Provided' : 'Missing'}</dd>
                </div>
                <div>
                  <dt>Wrong-fix control</dt>
                  <dd>{task.hasDistractor ? 'Provided' : 'Not provided'}</dd>
                </div>
                <div>
                  <dt>Family</dt>
                  <dd>{task.family === 'simbench' ? 'Device operation' : 'Code generation'}</dd>
                </div>
              </dl>
              <Link to="/run" search={{ task: task.id }} className="text-link">
                Inspect run options <PlayIcon />
              </Link>
            </section>
            <section className="quiet-panel">
              <h3>One result, one scope</h3>
              <p>
                Source checks assess submitted code. Native UI claims need a recorded simulator run.
              </p>
              <code>{task.path}</code>
            </section>
          </aside>
        </div>
      )}
      {tab === 'checks' && (
        <div className="checks-view">
          <div className="section-heading">
            <h2>What a good answer must do</h2>
            <Badge>{task.checks ? `${task.checks} rubric checks` : 'State + event checks'}</Badge>
          </div>
          {task.criteria.length ? (
            task.criteria.map((criterion, i) => (
              <article className="criterion" key={criterion.id}>
                <span className="criterion-number">{String(i + 1).padStart(2, '0')}</span>
                <div>
                  <h3>{criterion.name.replaceAll('-', ' ')}</h3>
                  <p>{criterion.description}</p>
                  <small>
                    {task.policyCriteria.includes(criterion.id)
                      ? 'Policy contract'
                      : graders[criterion.grading.kind].label}{' '}
                    · weight {criterion.weight}
                  </small>
                </div>
              </article>
            ))
          ) : (
            <Notice>
              Device tasks verify final app state and event order in <code>tests/verify.py</code>.
              Use the repository’s simulator calibration commands before treating a result as
              validated.
            </Notice>
          )}
          {task.measurements.includes('policy-behavior') && (
            <Notice>
              <CheckCircleIcon />
              This task also runs a deterministic JavaScript policy contract. A source judge’s
              approval cannot override a failed contract.
            </Notice>
          )}
          <details className="panel">
            <summary>Declared calibration brackets</summary>
            <pre className="code-preview">{JSON.stringify(task.calibration, null, 2)}</pre>
          </details>
        </div>
      )}
      {tab === 'files' && <TaskFiles task={task} />}
      {tab === 'attempts' && <TrialTable trials={trials} />}
    </>
  )
}
function TaskFiles({ task }: { task: TaskDetail }) {
  const [selected, setSelected] = useState(task.files[0])
  return (
    <div className="file-browser">
      <aside className="file-tree">
        {['environment', 'reference', 'distractor', 'checks'].map((area) => (
          <div key={area}>
            <h3>{area === 'environment' ? 'Starting workspace' : area}</h3>
            {task.files
              .filter((f) => f.area === area)
              .map((file) => (
                <button
                  className={
                    selected?.area === area && selected?.path === file.path ? 'selected' : ''
                  }
                  key={file.path}
                  onClick={() => setSelected(file)}
                >
                  <FileIcon />
                  <span>{file.path}</span>
                </button>
              ))}
          </div>
        ))}
      </aside>
      <div className="file-content">
        {selected ? (
          <>
            <div className="file-bar">
              <FileIcon />
              {selected.area}/{selected.path}
              <Badge>{selected.bytes.toLocaleString()} B</Badge>
            </div>
            <FilePreview
              key={`${selected.area}/${selected.path}`}
              queryKey={['task-file', task.id, selected.area, selected.path]}
              load={() =>
                getTaskFile({
                  data: {
                    task: task.id,
                    area: selected.area as 'environment' | 'reference' | 'distractor' | 'checks',
                    path: selected.path,
                  },
                })
              }
            />
          </>
        ) : (
          <p>No previewable files.</p>
        )}
      </div>
    </div>
  )
}
