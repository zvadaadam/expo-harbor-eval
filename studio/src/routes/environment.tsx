import { createFileRoute } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { environmentQuery } from '../lib/queries'
import { Badge, PageHeader } from '../components/ui'
import { LaptopIcon, TerminalIcon } from '../components/icons'

export const Route = createFileRoute('/environment')({
  loader: ({ context }) => context.queryClient.ensureQueryData(environmentQuery),
  component: Environment,
})
function Environment() {
  const { data } = useSuspenseQuery(environmentQuery)
  return (
    <>
      <PageHeader
        title="Local environment"
        description="Check your local setup and find your task files."
      />
      <div className="environment-grid">
        <section className="panel">
          <span className="feature-icon">
            <LaptopIcon />
          </span>
          <h2>{data.repository}</h2>
          <Badge tone="green" dot>
            Local workspace
          </Badge>
          <dl className="detail-list">
            <div>
              <dt>Task definitions</dt>
              <dd>
                <code>{data.taskStorage}</code>
              </dd>
            </div>
            <div>
              <dt>Saved drafts</dt>
              <dd>
                <code>{data.draftStorage}</code>
              </dd>
            </div>
            <div>
              <dt>Run results</dt>
              <dd>
                <code>{data.runStorage}</code>
              </dd>
            </div>
            <div>
              <dt>Exported tasks</dt>
              <dd>
                <code>outputs/studio/</code>
              </dd>
            </div>
          </dl>
        </section>
        <section className="panel">
          <span className="feature-icon">
            <TerminalIcon />
          </span>
          <h2>Evaluator</h2>
          <Badge tone={data.installedVersion === data.harborVersion ? 'green' : 'amber'}>
            Harbor {data.installedVersion ?? 'not installed'} ·{' '}
            {data.installedVersion === data.harborVersion
              ? 'Matches repository pin'
              : `Requires ${data.harborVersion}`}
          </Badge>
          {data.installedVersion !== data.harborVersion && (
            <>
              <p>Install the required evaluator from the repository root:</p>
              <pre className="mini-code">uv sync --frozen</pre>
            </>
          )}
        </section>
      </div>
    </>
  )
}
