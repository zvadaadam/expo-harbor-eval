import { promises as fs } from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { draftSchema, jobSchema, localIdSchema, type Draft, type Job } from '../lib/schema'

/** Local state stays outside Harbor's task discovery and evaluator fingerprint. */
export class StudioStore {
  constructor(readonly root: string) {}

  async safePath(...parts: string[]) {
    const target = path.resolve(this.root, '.studio', ...parts)
    const relative = path.relative(this.root, target)
    if (relative.startsWith('..') || path.isAbsolute(relative))
      throw new Error('Invalid local state path.')
    let current = this.root
    for (const segment of relative.split(path.sep)) {
      current = path.join(current, segment)
      try {
        if ((await fs.lstat(current)).isSymbolicLink())
          throw new Error('Studio does not follow symlinked state paths.')
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      }
    }
    return target
  }

  async atomicWrite(file: string, value: unknown) {
    const temp = `${file}.${randomUUID()}.tmp`
    try {
      await fs.writeFile(temp, JSON.stringify(value, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
      await fs.rename(temp, file)
    } finally {
      await fs.rm(temp, { force: true })
    }
  }

  async readDraft(id: string): Promise<Draft> {
    localIdSchema.parse(id)
    const file = await this.safePath('drafts', `${id}.json`)
    return draftSchema.parse(JSON.parse(await fs.readFile(file, 'utf8')))
  }

  async listDrafts() {
    const directory = await this.safePath('drafts')
    const names = await fs.readdir(directory).catch((error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') return []
      throw error
    })
    const drafts: Draft[] = []
    const warnings: string[] = []
    for (const name of names.filter((name) => name.endsWith('.json'))) {
      try {
        drafts.push(await this.readDraft(name.slice(0, -5)))
      } catch {
        warnings.push(`Could not read draft ${name}. The original file was kept.`)
      }
    }
    return { drafts: drafts.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)), warnings }
  }

  async saveDraft(input: Draft): Promise<Draft> {
    const draft = draftSchema.parse(input)
    const directory = await this.safePath('drafts')
    await fs.mkdir(directory, { recursive: true, mode: 0o700 })
    const lock = await this.safePath('drafts', `${draft.id}.lock`)
    try {
      await fs.mkdir(lock)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'EEXIST')
        throw new Error('Another save is in progress. Please retry.')
      throw error
    }
    try {
      let previous: Draft | undefined
      try {
        previous = await this.readDraft(draft.id)
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      }
      if ((previous?.revision ?? 0) !== draft.revision)
        throw new Error(
          'This draft changed in another tab. Reload it before saving; your edits are still in this editor.',
        )
      const saved = { ...draft, revision: draft.revision + 1, updatedAt: new Date().toISOString() }
      await this.atomicWrite(await this.safePath('drafts', `${draft.id}.json`), saved)
      return saved
    } finally {
      await fs.rmdir(lock)
    }
  }

  async listJobs(): Promise<Job[]> {
    const directory = await this.safePath('jobs')
    const names = await fs.readdir(directory).catch((error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') return []
      throw error
    })
    const jobs: Job[] = []
    for (const id of names.filter((name) => localIdSchema.safeParse(name).success)) {
      jobs.push(await this.readJob(id))
    }
    return jobs.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  }

  async readJob(id: string): Promise<Job> {
    localIdSchema.parse(id)
    return jobSchema.parse(
      JSON.parse(await fs.readFile(await this.safePath('jobs', id, 'state.json'), 'utf8')),
    )
  }

  async cancelJob(id: string) {
    const job = await this.readJob(id)
    if (['running', 'queued'].includes(job.status))
      await fs.writeFile(await this.safePath('jobs', id, 'cancel'), '', { mode: 0o600 })
    return job
  }
}
