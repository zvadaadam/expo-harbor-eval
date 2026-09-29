import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { useEffect, useRef } from 'react'
import { catalogQuery, runsQuery } from '../lib/queries'
import {
  Badge,
  categoryNames,
  Empty,
  measurementNames,
  Notice,
  PageHeader,
  readiness,
} from '../components/ui'
import {
  ArrowRightIcon,
  CodeIcon,
  DeviceIcon,
  GridIcon,
  ListIcon,
  PlusIcon,
  SearchIcon,
} from '../components/icons'

const searchSchema = z.object({
  q: z.string().catch('').default(''),
  category: z.string().catch('all').default('all'),
  view: z.enum(['grid', 'list']).catch('grid').default('grid'),
})
export const Route = createFileRoute('/')({
  validateSearch: searchSchema,
  loader: ({ context }) =>
    Promise.all([
      context.queryClient.ensureQueryData(catalogQuery),
      context.queryClient.ensureQueryData(runsQuery),
    ]),
  component: Library,
})

function Library() {
  const { data: catalog } = useSuspenseQuery(catalogQuery)
  const { data: runs } = useSuspenseQuery(runsQuery)
  const search = Route.useSearch()
  const searchInput = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (
        event.key === '/' &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !target.isContentEditable &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      ) {
        event.preventDefault()
        searchInput.current?.focus()
      }
    }
    window.addEventListener('keydown', focusSearch)
    return () => window.removeEventListener('keydown', focusSearch)
  }, [])
  const navigate = useNavigate({ from: '/' })
  const setSearch = (patch: Partial<typeof search>) =>
    void navigate({ search: { ...search, ...patch }, replace: true, resetScroll: false })
  const tasks = catalog.tasks.filter(
    (t) =>
      (search.category === 'all' || t.category === search.category) &&
      `${t.title} ${t.id} ${t.description}`.toLowerCase().includes(search.q.toLowerCase()),
  )
  const runCounts = new Map<string, number>()
  runs.trials.forEach((trial) => runCounts.set(trial.task, (runCounts.get(trial.task) ?? 0) + 1))
  return (
    <>
      <PageHeader
        title="Tasks"
        description="Evaluation tasks for Expo and React Native. Browse a task or create your own."
        actions={
          <Link to="/new" className="button primary">
            <PlusIcon />
            New task
          </Link>
        }
      />
      {catalog.warnings.map((w) => (
        <Notice key={w} tone="warning">
          {w}
        </Notice>
      ))}
      <div className="category-tabs" aria-label="Task categories">
        {[['all', 'All tasks'], ...Object.entries(categoryNames)].map(([id, label]) => (
          <button
            key={id}
            className={search.category === id ? 'selected' : ''}
            onClick={() => setSearch({ category: id })}
          >
            {label}
            <span>
              {id === 'all'
                ? catalog.tasks.length
                : catalog.tasks.filter((t) => t.category === id).length}
            </span>
          </button>
        ))}
      </div>
      <div className="library-toolbar">
        <div className="library-search">
          <label htmlFor="task-search">Search tasks</label>
          <div className="search-field">
            <SearchIcon />
            <input
              id="task-search"
              ref={searchInput}
              aria-label="Search tasks"
              placeholder="Search tasks by name or behavior"
              value={search.q}
              onChange={(e) => setSearch({ q: e.target.value })}
            />
            <kbd>/</kbd>
          </div>
        </div>
        <div className="toolbar-right">
          <div className="view-toggle" aria-label="Layout">
            <button
              title="Card view"
              aria-label="Card view"
              aria-pressed={search.view === 'grid'}
              onClick={() => setSearch({ view: 'grid' })}
            >
              <GridIcon />
            </button>
            <button
              title="List view"
              aria-label="List view"
              aria-pressed={search.view === 'list'}
              onClick={() => setSearch({ view: 'list' })}
            >
              <ListIcon />
            </button>
          </div>
        </div>
      </div>
      <div className="section-caption">
        <span>
          {tasks.length} {tasks.length === 1 ? 'task' : 'tasks'}
        </span>
        <span>
          {catalog.tasks.filter((task) => task.family === 'expo-codegen').length} coding ·{' '}
          {catalog.tasks.filter((task) => task.family === 'simbench').length} simulator ·{' '}
          {runs.trials.length} recorded attempts
        </span>
      </div>
      {tasks.length ? (
        <div className={`task-grid ${search.view === 'list' ? 'task-list' : ''}`}>
          {tasks.map((task) => (
            <article className="task-card" key={task.id}>
              <Link className="task-card-link" to="/tasks/$taskId" params={{ taskId: task.id }}>
                <div className="card-top">
                  <span
                    className={`task-icon ${task.family === 'simbench' ? 'purple' : task.category === 'expo-sdk' ? 'green' : 'blue'}`}
                  >
                    {task.family === 'simbench' ? <DeviceIcon /> : <CodeIcon />}
                  </span>
                  <Badge>{task.difficulty}</Badge>
                </div>
                <div className="card-body">
                  <span className="card-category">
                    {categoryNames[task.category] ?? task.category}
                  </span>
                  <h3>{task.title}</h3>
                  <p>{task.description}</p>
                </div>
                <div className="card-measurements">
                  {task.measurements.map((m) => (
                    <span key={m}>
                      {measurementNames[m]}
                      {m === 'native-ui' ? ' · experimental' : ''}
                    </span>
                  ))}
                </div>
                <div className="card-footer">
                  <span className={`readiness ${task.held ? 'amber' : ''}`}>
                    <span className="dot" />
                    {readiness(task.validation)}
                  </span>
                  <span>
                    {runCounts.get(task.id) ?? 0} attempts <ArrowRightIcon />
                  </span>
                </div>
              </Link>
              <div className="card-actions">
                <Link
                  to="/tasks/$taskId/edit"
                  params={{ taskId: task.id }}
                  className="button quiet"
                  aria-label={`Edit ${task.title}`}
                >
                  Edit
                </Link>
                <Link
                  to="/run"
                  search={{ task: task.id }}
                  className="button secondary"
                  aria-label={`Run ${task.title}`}
                >
                  Run task
                </Link>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="No tasks match"
          action={
            <button
              className="button secondary"
              onClick={() => setSearch({ q: '', category: 'all' })}
            >
              Clear filters
            </button>
          }
        >
          Try a different search or category.
        </Empty>
      )}
    </>
  )
}
