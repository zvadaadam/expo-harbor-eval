import { createFileRoute, Link } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { trialQuery } from '../lib/queries'
import { getArtifact } from '../lib/api'
import {
  Badge,
  count,
  humanize,
  measurementNames,
  Metric,
  Notice,
  PageHeader,
  Status,
} from '../components/ui'
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  XCircleIcon,
  FileIcon,
  ClockIcon,
} from '../components/icons'
import { FilePreview } from '../components/file-preview'

export const Route = createFileRoute('/attempts/$trialId')({
  loader: ({ params, context }) => context.queryClient.ensureQueryData(trialQuery(params.trialId)),
  component: Attempt,
})
function Attempt() {
  const { trialId } = Route.useParams()
  const { data: trial } = useSuspenseQuery(trialQuery(trialId))
  const [artifact, setArtifact] = useState(
    trial.artifacts.find((a) => a.path.includes('reward-details'))?.path ??
      trial.artifacts[0]?.path ??
      '',
  )
  const [check, setCheck] = useState(
    trial.checks.findIndex((c) => c.passed === false) >= 0
      ? trial.checks.findIndex((c) => c.passed === false)
      : 0,
  )
  return (
    <>
      <Link to="/runs" className="back-link">
        <ArrowLeftIcon />
        All runs
      </Link>
      <PageHeader
        eyebrow={trial.run}
        title={humanize(trial.task.replace(/^(feedback|sdk|ui|router|simbench-ios)-\d+-/, ''))}
        description={trial.model || trial.agent}
        actions={<Status status={trial.outcome} />}
      />
      <div className="task-meta">
        <Badge tone="blue">{measurementNames[trial.measurement] ?? trial.measurement}</Badge>
        <Badge>{trial.backend}</Badge>
        {trial.regradeOf && <Badge tone="purple">Saved-answer regrade</Badge>}
        <Link to="/tasks/$taskId" params={{ taskId: trial.task }} className="text-link">
          View task
        </Link>
      </div>
      {trial.error && <Notice tone="error">{trial.error}</Notice>}
      {trial.regradeOf && (
        <Notice>
          This replays a saved submission. No new agent generation. Original submission:{' '}
          <code>{trial.regradeOf.split('/').at(-1)}</code>
        </Notice>
      )}
      <div className="metrics">
        <Metric
          value={trial.reward === null ? '—' : trial.reward.toFixed(2)}
          label="Recorded reward"
          detail={
            trial.reward === null ? 'No valid score recorded' : 'Within this measurement only'
          }
        />
        <Metric
          value={trial.cost === null ? 'Unknown' : `$${trial.cost.toFixed(3)}`}
          label="Reported generation usage"
          detail="Judge cost is not included"
        />
        <Metric value={count(trial.inputTokens)} label="Input tokens" />
        <Metric value={count(trial.outputTokens)} label="Output tokens" />
      </div>
      <div className="evidence-layout">
        <section className="check-rail">
          <div className="panel-heading">
            <h2>Recorded checks</h2>
            <Badge>{trial.checks.length}</Badge>
          </div>
          {trial.checks.length ? (
            trial.checks.map((item, i) => (
              <button
                key={`${item.name}-${i}`}
                className={`check-choice ${check === i ? 'selected' : ''}`}
                onClick={() => setCheck(i)}
              >
                {item.passed === true ? (
                  <CheckCircleIcon className="green" />
                ) : item.passed === false ? (
                  <XCircleIcon className="red" />
                ) : (
                  <ClockIcon />
                )}
                <span>{humanize(item.name)}</span>
              </button>
            ))
          ) : (
            <p className="muted-pad">No per-check evidence was recorded.</p>
          )}
          {trial.checks[check] && (
            <div className="check-explanation">
              <span className="eyebrow">RECORDED EXPLANATION</span>
              <p>{trial.checks[check].detail}</p>
            </div>
          )}
        </section>
        <section className="evidence-pane">
          <div className="file-bar">
            <FileIcon />
            <label className="visually-hidden" htmlFor="artifact">
              Evidence artifact
            </label>
            <select id="artifact" value={artifact} onChange={(e) => setArtifact(e.target.value)}>
              {trial.artifacts.map((a) => (
                <option key={a.path} value={a.path}>
                  {a.path}
                </option>
              ))}
            </select>
            <Badge>Original file</Badge>
          </div>
          {artifact ? (
            <FilePreview
              key={artifact}
              queryKey={['artifact', trialId, artifact]}
              load={() => getArtifact({ data: { id: trialId, path: artifact } })}
            />
          ) : (
            <Notice>No previewable artifacts are available.</Notice>
          )}
        </section>
      </div>
      <details className="panel provenance">
        <summary>Task and evaluator provenance</summary>
        <pre className="code-preview">{JSON.stringify(trial.provenance, null, 2)}</pre>
      </details>
    </>
  )
}
