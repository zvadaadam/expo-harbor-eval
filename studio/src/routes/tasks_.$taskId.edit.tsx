import { createFileRoute } from '@tanstack/react-router'
import { getTaskEdit } from '../lib/api'
import { TaskEditor } from '../components/task-editor'

export const Route = createFileRoute('/tasks_/$taskId/edit')({
  loader: ({ params }) => getTaskEdit({ data: params.taskId }),
  component: EditTask,
})

function EditTask() {
  const edit = Route.useLoaderData()
  return <TaskEditor key={edit.draft.sourceTask} initial={edit.draft} editing={edit} />
}
