import { test } from 'node:test'
import assert from 'node:assert/strict'
import { promises as fs } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { StudioStore } from './store'
import { blankDraft } from '../lib/editor-store'
import { draftIssues, draftSchema } from '../lib/schema'
import { taskSlug, nextCheckId } from '../lib/grading'

test('draft saves persist across store instances and stale revisions cannot overwrite', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'studio-store-'))
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  const store = new StudioStore(root)
  const draft = blankDraft(randomUUID())
  const saved = await store.saveDraft({ ...draft, title: 'First save' })
  assert.equal(saved.revision, 1)
  assert.equal((await new StudioStore(root).readDraft(draft.id)).title, 'First save')
  await assert.rejects(store.saveDraft({ ...draft, title: 'Stale edit' }), /changed in another tab/)
  const next = await store.saveDraft({ ...saved, title: 'Second save' })
  assert.equal(next.revision, 2)
  assert.equal((await store.listDrafts()).drafts.length, 1)
  assert.equal(await fs.stat(path.join(root, 'tasks')).catch(() => null), null)
})

test('concurrent writers cannot silently overwrite each other', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'studio-race-'))
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  const store = new StudioStore(root)
  const draft = await store.saveDraft(blankDraft(randomUUID()))
  const writes = await Promise.allSettled([
    store.saveDraft({ ...draft, title: 'A' }),
    store.saveDraft({ ...draft, title: 'B' }),
  ])
  assert.equal(writes.filter((r) => r.status === 'fulfilled').length, 1)
  assert.equal((await store.readDraft(draft.id)).revision, 2)
})

test('draft state rejects directory symlinks and traversal', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'studio-path-'))
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  const store = new StudioStore(root)
  const external = path.join(root, 'other')
  await fs.mkdir(external)
  await fs.mkdir(path.join(root, '.studio'))
  await fs.symlink(external, path.join(root, '.studio/drafts'))
  await assert.rejects(store.saveDraft(blankDraft(randomUUID())), /symlink/)
  await assert.rejects(store.readDraft('../../other/private'), /./)
  assert.deepEqual(await fs.readdir(external), [])
})

test('draft validation blocks unsafe paths, collisions, and unsupported calibration inputs', () => {
  const draft = blankDraft(randomUUID())
  assert.equal(
    draftSchema.safeParse({
      ...draft,
      files: [{ area: 'environment', path: '../escape.ts', content: '' }],
    }).success,
    false,
  )
  assert.equal(
    draftSchema.safeParse({ ...draft, files: [draft.files[0], draft.files[0]] }).success,
    false,
  )
  assert.equal(
    draftSchema.safeParse({ ...draft, criteria: [draft.criteria[0], draft.criteria[0]] }).success,
    false,
  )
  assert.ok(
    draftIssues({
      ...draft,
      files: [{ area: 'environment', path: 'App.js', content: 'code' }],
    }).some((issue) => issue.includes('TSX')),
  )
  assert.ok(
    draftIssues({ ...draft, baselineMustFail: [] }).some((issue) =>
      issue.includes('commented baseline'),
    ),
  )
})

test('old drafts migrate to source review and incomplete checks can be saved, but not exported', () => {
  const draft = blankDraft(randomUUID())
  const { grading: _grading, ...oldCheck } = draft.criteria[0]
  const migrated = draftSchema.parse({ ...draft, criteria: [oldCheck] })
  assert.equal(migrated.criteria[0].grading.kind, 'ai-review')
  draft.criteria[0].grading = { kind: 'file-exists', config: { path: '' } }
  assert.equal(draftSchema.safeParse(draft).success, true)
  assert.ok(draftIssues(draft).some((issue) => issue.includes('File path is required')))
  draft.criteria[0].grading = {
    kind: 'json-key-equals',
    config: { path: 'package.json', key: 'main', expected: 'not json' },
  }
  assert.ok(draftIssues(draft).some((issue) => issue.includes('valid JSON')))
  draft.criteria[0].grading = { kind: 'test-script', config: { script: '../private.py' } }
  assert.ok(draftIssues(draft).some((issue) => issue.includes('relative path')))
  assert.equal(
    draftSchema.safeParse({
      ...draft,
      criteria: [{ ...oldCheck, grading: { kind: 'fake', config: {} } }],
    }).success,
    false,
  )
})

test('generated identifiers remain valid and cannot collide after removing checks', () => {
  assert.equal(taskSlug('Fix résumé / Expo Router!'), 'fix-resume-expo-router')
  assert.equal(nextCheckId([{ id: 'check-1' }, { id: 'check-3' }]), 'check-2')
})

test('all categories and simulator drafts survive persistence without coding requirements', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'studio-simulator-draft-'))
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  const draft = draftSchema.parse({
    ...blankDraft(randomUUID()),
    title: 'Create a note',
    slug: 'create-a-note',
    category: 'simbench',
    instruction: 'Create the requested note through the app UI and preserve the matching UI event.',
    motivation: 'Simulator authoring regression',
    criteria: [],
    mustFail: [],
    baselineMustFail: [],
    simulator: {
      template: 'simbench-ios-01-goldennotes-create-note',
      fingerprint: 'a'.repeat(64),
      tier: 'forms-and-keyboard',
    },
    files: [
      { area: 'checks', path: 'verify.py', content: '# Fixture verifier' },
      { area: 'reference', path: 'oracle.py', content: '# Fixture oracle' },
      { area: 'environment', path: 'app-src/GoldenNotes.swift', content: '// Fixture app' },
      { area: 'environment', path: 'app-src/Info.plist', content: '<plist/>' },
    ],
  })
  assert.deepEqual(draftIssues(draft), [])
  const saved = await new StudioStore(root).saveDraft(draft)
  assert.deepEqual((await new StudioStore(root).readDraft(saved.id)).simulator, draft.simulator)
  assert.ok(
    draftIssues({ ...draft, simulator: null }).some((issue) =>
      issue.includes('Choose a simulator'),
    ),
  )
})

test('numeric grader settings and scoring options validate without rejecting partial drafts', () => {
  const draft = blankDraft(randomUUID())
  draft.criteria[0].grading = {
    kind: 'image-size-equals',
    config: { path: 'screen.png', width: '1.5', height: '400' },
  }
  assert.equal(draftSchema.safeParse(draft).success, true)
  assert.ok(
    draftIssues(draft).some((issue) => issue.includes('Width (pixels) must be a valid integer')),
  )
  draft.criteria[0].grading = { kind: 'trajectory-turn-count', config: { max_turns: '20' } }
  assert.ok(!draftIssues(draft).some((issue) => issue.startsWith('Check 1:')))
  draft.criteria[0].weight = -1
  assert.ok(draftIssues(draft).includes('Negative weights require weighted sum scoring.'))
  draft.scoring.aggregation = 'weighted-sum'
  assert.ok(!draftIssues(draft).includes('Negative weights require weighted sum scoring.'))
})
