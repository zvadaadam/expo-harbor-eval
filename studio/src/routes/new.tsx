import { createFileRoute } from '@tanstack/react-router'
import { getBlankDraft } from '../lib/api'
import { TaskEditor } from '../components/task-editor'

export const Route = createFileRoute('/new')({
  loader: () => getBlankDraft(),
  component: () => <TaskEditor initial={Route.useLoaderData()} />,
})
