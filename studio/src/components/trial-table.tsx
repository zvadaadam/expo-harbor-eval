import { Link } from '@tanstack/react-router'
import type { Trial } from '../lib/schema'
import { Badge, date, Empty, humanize, measurementNames, Status } from './ui'
import { ArrowUpRightIcon } from './icons'

export function TrialTable({ trials }: { trials: Trial[] }) {
  if (!trials.length)
    return (
      <Empty title="No attempts yet">
        Run a local control to get your first piece of evidence.
      </Empty>
    )
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Task / run</th>
            <th>Agent</th>
            <th>Measurement</th>
            <th>Outcome</th>
            <th>Recorded</th>
            <th>
              <span className="visually-hidden">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {trials.map((trial) => (
            <tr key={trial.id}>
              <td>
                <Link
                  className="table-title"
                  to="/attempts/$trialId"
                  params={{ trialId: trial.id }}
                >
                  {humanize(trial.task.replace(/^(feedback|sdk|ui|router|simbench-ios)-\d+-/, ''))}
                </Link>
                <small>{trial.run}</small>
              </td>
              <td>
                <span className="model-name">{trial.model || trial.agent}</span>
                {trial.regradeOf && <Badge tone="purple">Regrade</Badge>}
              </td>
              <td>
                <Badge>{measurementNames[trial.measurement] ?? trial.measurement}</Badge>
              </td>
              <td>
                <Status status={trial.outcome} />
              </td>
              <td className="nowrap secondary-text">{date(trial.startedAt)}</td>
              <td>
                <Link
                  className="icon-link"
                  aria-label={`Open ${trial.name}`}
                  to="/attempts/$trialId"
                  params={{ trialId: trial.id }}
                >
                  <ArrowUpRightIcon />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
