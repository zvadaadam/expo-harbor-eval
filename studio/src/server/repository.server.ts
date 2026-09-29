import { execFile, spawn } from 'node:child_process'
import { existsSync, promises as fs } from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { z } from 'zod'
import { StudioStore } from './store'
import {
  catalogSchema,
  draftFileSchema,
  draftSchema,
  draftIssues,
  fileContentSchema,
  runsSchema,
  taskDetailSchema,
  taskEditSchema,
  trialDetailSchema,
  type Draft,
  type JobPlan,
  type Job,
} from '../lib/schema'

function repositoryRoot() {
  let current = process.cwd()
  for (;;) {
    if (existsSync(path.join(current, 'pyproject.toml')) && existsSync(path.join(current, 'tasks')))
      return current
    const parent = path.dirname(current)
    if (parent === current)
      throw new Error('Start Studio from this repository or its studio directory.')
    current = parent
  }
}
const root = repositoryRoot()
export const store = new StudioStore(root)
const python =
  process.env.STUDIO_PYTHON ||
  (existsSync(path.join(root, '.venv/bin/python'))
    ? path.join(root, '.venv/bin/python')
    : 'python3')

export function bridge(request: Record<string, unknown>): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      python,
      [path.join(root, 'studio/bridge/catalog.py')],
      {
        cwd: root,
        timeout: 30_000,
        maxBuffer: 12_000_000,
      },
      (error, stdout, stderr) => {
        if (error)
          return reject(
            new Error(
              stderr.trim().slice(0, 1000) ||
                'The repository reader failed. Check Python 3.12+ is available.',
            ),
          )
        try {
          resolve(JSON.parse(stdout))
        } catch {
          reject(new Error('The repository reader returned invalid JSON.'))
        }
      },
    )
    child.stdin?.end(JSON.stringify(request))
  })
}
export async function catalog() {
  return catalogSchema.parse(await bridge({ action: 'catalog' }))
}
export async function task(id: string) {
  return taskDetailSchema.parse(await bridge({ action: 'task', task: id }))
}
export async function editTask(id: string) {
  return taskEditSchema.parse(await bridge({ action: 'edit-task', task: id }))
}
export async function updateTask(input: { task: string; fingerprint: string; draft: Draft }) {
  return taskEditSchema.parse(await bridge({ action: 'update-task', ...input }))
}
export async function runs() {
  return runsSchema.parse(await bridge({ action: 'runs' }))
}
export async function trial(id: string) {
  return trialDetailSchema.parse(await bridge({ action: 'trial', id }))
}
export async function file(request: Record<string, unknown>) {
  return fileContentSchema.parse(await bridge(request))
}

export async function duplicate(id: string): Promise<Draft> {
  const result = z
    .object({
      task: taskDetailSchema,
      files: z.array(draftFileSchema),
      simulator: draftSchema.shape.simulator,
    })
    .parse(await bridge({ action: 'duplicate', task: id }))
  const source = result.task
  const bracket = z.object({ must_fail: z.array(z.string()) })
  return store.saveDraft({
    id: randomUUID(),
    revision: 0,
    title: `${source.title} — copy`,
    slug: `${source.id}-copy`,
    category: source.category as Draft['category'],
    difficulty: source.difficulty as Draft['difficulty'],
    motivation: source.motivation,
    instruction: source.instruction,
    sourceTask: source.id,
    simulator: result.simulator,
    scoring: source.scoring,
    criteria: source.criteria,
    files: result.files,
    mustFail: bracket.safeParse(source.calibration.distractor).data?.must_fail ?? [],
    baselineMustFail:
      bracket.safeParse(source.calibration['baseline-comment']).data?.must_fail ?? [],
    updatedAt: '',
  })
}

export async function simulatorTemplate(id: string) {
  return z
    .object({
      task: taskDetailSchema,
      files: z.array(draftFileSchema),
      simulator: draftSchema.shape.simulator,
    })
    .parse(await bridge({ action: 'simulator-template', task: id }))
}

export async function exportDraft(id: string, revision: number) {
  const draft = await store.readDraft(id)
  if (draft.revision !== revision)
    throw new Error('The saved draft changed. Reload it before exporting.')
  const issues = draftIssues(draft)
  if (issues.length) throw new Error(issues.join(' '))
  return z
    .object({ path: z.string(), files: z.array(z.string()) })
    .parse(await bridge({ action: 'export', draft }))
}

export async function startJob(plan: JobPlan): Promise<Job> {
  const definition = await task(plan.task)
  if (definition.held || definition.family !== 'expo-codegen')
    throw new Error(
      'Local controls currently support available coding tasks. Device calibration uses the repository CLI.',
    )
  if (plan.action === 'policy' && !definition.measurements.includes('policy-behavior'))
    throw new Error('This task does not have an executable policy contract.')
  const runtime = await environment()
  if (!runtime.evaluator || runtime.installedVersion !== runtime.harborVersion)
    throw new Error(
      `Run uv sync --frozen in the repository to install Harbor ${runtime.harborVersion}. The selected Python has ${runtime.installedVersion ?? 'no Harbor installation'}.`,
    )
  const active = (await store.listJobs()).filter((job) =>
    ['running', 'queued'].includes(job.status),
  )
  if (active.length >= 3)
    throw new Error('Three controls are already active or queued. Wait for one to finish.')
  const job: Job = {
    ...plan,
    id: randomUUID(),
    status: 'queued',
    createdAt: new Date().toISOString(),
  }
  const directory = await store.safePath('jobs', job.id)
  await fs.mkdir(directory, { recursive: true, mode: 0o700 })
  await store.atomicWrite(path.join(directory, 'state.json'), job)
  const worker = spawn(
    python,
    [path.join(root, 'studio/bridge/worker.py'), job.id, String(process.pid)],
    {
      cwd: root,
      detached: true,
      stdio: 'ignore',
    },
  )
  worker.on('error', async () => {
    await store.atomicWrite(path.join(directory, 'state.json'), {
      ...job,
      status: 'failed',
      message: 'Could not start the Python worker.',
      finishedAt: new Date().toISOString(),
    })
  })
  worker.unref()
  return job
}

export async function jobDetail(id: string) {
  const job = await store.readJob(id)
  const logPath = await store.safePath('jobs', id, 'log.txt')
  let log = ''
  try {
    const handle = await fs.open(logPath, 'r')
    try {
      const { size } = await handle.stat()
      const buffer = Buffer.alloc(Math.min(size, 200_000))
      await handle.read(buffer, 0, buffer.length, Math.max(0, size - buffer.length))
      log = (size > buffer.length ? '[Showing the last 200 KB]\n' : '') + buffer.toString('utf8')
    } finally {
      await handle.close()
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
  return { job, log }
}

export async function modelPlan(input: { task: string; effort: string; attempts: number }) {
  const definition = await task(input.task)
  if (definition.held || definition.family !== 'expo-codegen')
    throw new Error('Choose an available coding task for a Sonnet plan.')
  // A downloadable plan, never an automatic paid launch or a claimed hard cap.
  const config = {
    jobs_dir: 'runs',
    n_attempts: input.attempts,
    n_concurrent_trials: 1,
    environment: {
      import_path: 'expo_harbor_evals.mac_sandbox_env:MacSandboxEnvironment',
      delete: true,
    },
    verifier: {
      env: {
        EXPO_EVAL_VERIFIER_MODE: 'judge',
        REWARDKIT_JUDGE: 'claude-code',
        REWARDKIT_MODEL: 'sonnet',
      },
    },
    agents: [
      {
        import_path: 'expo_harbor_evals.claude_host_agent:ClaudeHostAgent',
        model_name: `sonnet@${input.effort}`,
      },
    ],
    datasets: [{ path: 'tasks/codegen', task_names: [definition.id] }],
  }
  return {
    filename: `${definition.id}-${input.effort}.json`,
    content: JSON.stringify(config, null, 2) + '\n',
  }
}

export async function environment() {
  const project = await fs.readFile(path.join(root, 'pyproject.toml'), 'utf8')
  const harborVersion = project.match(/"harbor==([^"]+)"/)?.[1]
  if (!harborVersion) throw new Error('The repository must pin its Harbor version.')
  const installedVersion = await new Promise<string | null>((resolve) => {
    execFile(
      python,
      [
        '-c',
        'import importlib.metadata, pathlib, sys; assert (pathlib.Path(sys.executable).parent / "harbor").is_file(); print(importlib.metadata.version("harbor"))',
      ],
      { timeout: 5000 },
      (error, stdout) => resolve(error ? null : stdout.trim()),
    )
  })
  return {
    repository: path.basename(root),
    evaluator: !!installedVersion,
    installedVersion,
    taskStorage: 'tasks/',
    draftStorage: '.studio/drafts/',
    runStorage: 'runs/',
    harborVersion,
  }
}

export async function action<T>(
  fn: () => Promise<T>,
): Promise<{ ok: true; value: T } | { ok: false; message: string }> {
  try {
    return { ok: true, value: await fn() }
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : 'The local action failed.',
    }
  }
}
