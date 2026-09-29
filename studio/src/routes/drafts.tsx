import { createFileRoute, Link } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { draftsQuery } from '../lib/queries'
import { Badge, date, Empty, Notice, PageHeader } from '../components/ui'
import { ArrowRightIcon, BookIcon, PlusIcon } from '../components/icons'

export const Route = createFileRoute('/drafts')({
  loader: ({ context }) => context.queryClient.ensureQueryData(draftsQuery),
  component: Drafts,
})
function Drafts() {
  const { data } = useSuspenseQuery(draftsQuery)
  return (
    <>
      <PageHeader
        title="Your drafts"
        description="Saved tasks you’re still working on."
        actions={
          <Link to="/new" className="button primary">
            <PlusIcon />
            New task
          </Link>
        }
      />
      {data.warnings.map((w) => (
        <Notice key={w} tone="warning">
          {w}
        </Notice>
      ))}
      {data.drafts.length ? (
        <div className="draft-grid">
          {data.drafts.map((draft) => (
            <Link
              key={draft.id}
              to="/drafts/$draftId"
              params={{ draftId: draft.id }}
              className="draft-card"
            >
              <span className="task-icon blue">
                <BookIcon />
              </span>
              <div>
                <h2>{draft.title || 'Untitled task'}</h2>
                <p>{draft.instruction.slice(0, 130) || 'Start shaping your evaluation task.'}</p>
                <div className="draft-meta">
                  <Badge>Draft · v{draft.revision}</Badge>
                  <span>Saved {date(draft.updatedAt)}</span>
                </div>
              </div>
              <ArrowRightIcon />
            </Link>
          ))}
        </div>
      ) : (
        <Empty
          title="No drafts yet"
          action={
            <Link to="/new" className="button primary">
              <PlusIcon />
              Create a task
            </Link>
          }
        >
          Create a task or duplicate one from the library.
        </Empty>
      )}
    </>
  )
}
