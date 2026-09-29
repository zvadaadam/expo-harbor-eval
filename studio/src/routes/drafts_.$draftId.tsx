import { createFileRoute } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { draftQuery } from '../lib/queries'
import { TaskEditor } from '../components/task-editor'

export const Route = createFileRoute('/drafts_/$draftId')({
  loader: ({ params, context }) => context.queryClient.ensureQueryData(draftQuery(params.draftId)),
  component: DraftPage,
})
function DraftPage() {
  const { draftId } = Route.useParams()
  const { data } = useSuspenseQuery(draftQuery(draftId))
  return <TaskEditor key={draftId} initial={data} />
}
