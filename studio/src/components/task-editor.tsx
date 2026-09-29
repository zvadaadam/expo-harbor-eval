import { useEffect, useRef, useState } from 'react'
import { useStore } from 'zustand'
import { Link, useBlocker, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createEditorStore } from '../lib/editor-store'
import { catalogQuery } from '../lib/queries'
import simulatorTiers from '../lib/simulator-tiers.json'
import { GraderFields, CheckScoring } from './grading-fields'
import { draftIssues, draftSchema, filePathSchema, type Draft, type TaskEdit } from '../lib/schema'
import {
  graderOptions,
  graderGroups,
  aggregations,
  pythonCriterionTemplate,
  graders,
  nextCheckId,
  taskSlug,
  testScriptTemplate,
  type GraderKind,
} from '../lib/grading'
import { exportTask, saveDraft, updateTask, getSimulatorTemplate, unwrap } from '../lib/api'
import { BackLink, Badge, Button, categoryNames, Notice, PageHeader } from './ui'
import {
  CheckCircleIcon,
  CodeIcon,
  FileIcon,
  PlusIcon,
  PlayIcon,
  SaveIcon,
  ShieldIcon,
} from './icons'

export function TaskEditor({ initial, editing }: { initial: Draft; editing?: TaskEdit }) {
  const [fingerprint, setFingerprint] = useState(editing?.fingerprint ?? '')
  const gradingLocked = editing?.protectedGrading ?? false
  const saveLabel = editing ? 'Save changes' : 'Save draft'
  const [store] = useState(() => createEditorStore(initial))
  const { draft, dirty, patch, saved } = useStore(store)
  const native = draft.category === 'simbench'
  const codingDraft = useRef(initial.category !== 'simbench' ? initial : null)
  const simulatorDraft = useRef(initial.category === 'simbench' ? initial : null)
  const library = useQuery({ ...catalogQuery, enabled: native && !editing })
  const template = useMutation({
    mutationFn: async (task: string) => unwrap(await getSimulatorTemplate({ data: task })),
    onSuccess: (result) => {
      const current = store.getState().draft
      patch({
        simulator: result.simulator,
        sourceTask: result.task.id,
        files: result.files,
        criteria: [],
        mustFail: [],
        baselineMustFail: [],
        instruction:
          current.simulator || !current.instruction.trim()
            ? result.task.instruction
            : current.instruction,
        motivation: current.motivation || result.task.motivation,
        difficulty: result.task.difficulty as Draft['difficulty'],
      })
    },
  })
  const chooseCategory = (category: Draft['category']) => {
    if (category === 'simbench' && !native) {
      codingDraft.current = draft
      const previous = simulatorDraft.current
      patch({
        category,
        simulator: previous?.simulator ?? null,
        sourceTask: previous?.sourceTask ?? null,
        files: previous?.files ?? [],
        criteria: [],
        mustFail: [],
        baselineMustFail: [],
      })
    } else if (category !== 'simbench' && native) {
      simulatorDraft.current = draft
      const previous = codingDraft.current
      patch({
        category,
        simulator: null,
        sourceTask: previous?.sourceTask ?? null,
        files: previous?.files ?? [],
        criteria: previous?.criteria ?? [],
        mustFail: previous?.mustFail ?? [],
        baselineMustFail: previous?.baselineMustFail ?? [],
      })
    } else patch({ category })
  }
  const client = useQueryClient()
  const navigate = useNavigate()
  const blocker = useBlocker({
    shouldBlockFn: () => store.getState().dirty,
    enableBeforeUnload: dirty,
    withResolver: true,
  })
  const persist = async () => {
    const parsed = draftSchema.safeParse(store.getState().draft)
    if (!parsed.success)
      throw new Error(
        parsed.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`).join(' '),
      )
    const result = editing
      ? unwrap(await updateTask({ data: { task: initial.slug, fingerprint, draft: parsed.data } }))
      : null
    if (result) setFingerprint(result.fingerprint)
    const value = result?.draft ?? unwrap(await saveDraft({ data: parsed.data }))
    saved(value)
    if (editing) {
      void client.invalidateQueries({ queryKey: ['catalog'] })
      void client.invalidateQueries({ queryKey: ['task', initial.slug] })
      void client.invalidateQueries({ queryKey: ['task-file', initial.slug] })
    } else {
      client.setQueryData(['draft', value.id], value)
      void client.invalidateQueries({ queryKey: ['drafts'] })
    }
    return value
  }
  const save = useMutation({
    mutationFn: persist,
    onSuccess: (value) => {
      if (!editing && initial.revision === 0)
        void navigate({ to: '/drafts/$draftId', params: { draftId: value.id }, replace: true })
    },
  })
  const exportMutation = useMutation({
    mutationFn: async () => {
      const state = store.getState()
      const current = state.dirty || !state.draft.revision ? await persist() : state.draft
      return {
        ...unwrap(await exportTask({ data: { id: current.id, revision: current.revision } })),
        revision: current.revision,
      }
    },
  })
  const issues = draftIssues(draft)
  const hasJudge = draft.criteria.some((c) => c.grading.kind === 'ai-review')
  const hasTests =
    !native &&
    (draft.files.some((f) => f.area === 'checks') ||
      draft.criteria.some(
        (c) =>
          ['test-script', 'custom-python'].includes(c.grading.kind) ||
          c.grading.kind.startsWith('trajectory-'),
      ))
  const busy = save.isPending || exportMutation.isPending || template.isPending
  const updateCriterion = (index: number, change: Partial<Draft['criteria'][number]>) =>
    patch({ criteria: draft.criteria.map((c, i) => (i === index ? { ...c, ...change } : c)) })
  const chooseGrader = (index: number, kind: GraderKind) => {
    const criterion = draft.criteria[index]
    const config: Record<string, string> = Object.fromEntries(
      graders[kind].fields.map((field) => [field.key, field.default ?? '']),
    )
    let files = draft.files
    if (kind === 'test-script' || kind === 'custom-python') {
      config.script = `${criterion.id}.${kind === 'test-script' ? 'cjs' : 'py'}`
      if (!files.some((f) => f.area === 'checks' && f.path === config.script))
        files = [
          ...files,
          {
            area: 'checks',
            path: config.script,
            content: kind === 'test-script' ? testScriptTemplate : pythonCriterionTemplate,
          },
        ]
    }
    patch({
      files,
      criteria: draft.criteria.map((c, i) =>
        i === index
          ? {
              ...c,
              type: graders[kind].score === 'continuous' ? 'numeric' : 'binary',
              min: 0,
              max: 1,
              grading: { kind, config },
            }
          : c,
      ),
    })
  }
  return (
    <>
      <BackLink />
      <PageHeader
        title={editing || draft.revision ? 'Edit task' : 'Create a task'}
        description={
          editing
            ? 'Update this task’s prompt and requirements.'
            : 'Describe the problem. Choose how to check the answer.'
        }
        actions={
          <>
            {editing && (
              <Link to="/run" search={{ task: initial.slug }} className="button secondary">
                <PlayIcon />
                Run task
              </Link>
            )}
            <Badge tone={dirty ? 'amber' : 'neutral'}>
              {dirty
                ? 'Unsaved changes'
                : editing
                  ? 'Library task'
                  : draft.revision
                    ? `Saved · v${draft.revision}`
                    : 'New draft'}
            </Badge>
            <Button
              variant="primary"
              busy={save.isPending}
              disabled={busy || (!dirty && (draft.revision > 0 || !!editing))}
              onClick={() => save.mutate()}
            >
              <SaveIcon />
              {saveLabel}
            </Button>
          </>
        }
      />
      {save.error && <Notice tone="error">{save.error.message}</Notice>}
      {template.error && <Notice tone="error">{template.error.message}</Notice>}
      {editing && save.isSuccess && !dirty && (
        <Notice tone="success">
          Changes saved. Re-run calibration before using this revision in a benchmark.
        </Notice>
      )}
      {blocker.status === 'blocked' && (
        <LeaveDialog onStay={() => blocker.reset?.()} onLeave={() => blocker.proceed?.()} />
      )}
      <fieldset
        className={`editor-fieldset task-authoring ${native ? 'brief-only' : ''}`}
        disabled={busy}
      >
        <div className="authoring-main">
          <section className="panel form-section" aria-labelledby="task-brief-heading">
            <h2 id="task-brief-heading">The task</h2>
            <label>
              Title
              <input
                value={draft.title}
                maxLength={180}
                placeholder="Restore scroll position after navigating back"
                onChange={(e) =>
                  patch({
                    title: e.target.value,
                    ...(!editing && (!draft.slug || draft.slug === taskSlug(draft.title))
                      ? { slug: taskSlug(e.target.value) }
                      : {}),
                  })
                }
              />
            </label>
            <label>
              What should the agent do?
              <textarea
                rows={7}
                value={draft.instruction}
                maxLength={30000}
                placeholder="Describe the problem, the expected behavior, and anything the agent should preserve."
                onChange={(e) => patch({ instruction: e.target.value })}
              />
              <span className="field-hint">
                This is the prompt the agent receives. Markdown is supported.
              </span>
            </label>
            <details className="authoring-settings">
              <summary>
                Task settings <span>Category, task ID & source</span>
              </summary>
              <div className="form-grid">
                <label>
                  Category
                  <select
                    disabled={!!editing && native}
                    value={draft.category}
                    onChange={(e) => chooseCategory(e.target.value as Draft['category'])}
                  >
                    {Object.entries(categoryNames)
                      .filter(
                        ([id]) => !editing || (native ? id === 'simbench' : id !== 'simbench'),
                      )
                      .map(([id, name]) => (
                        <option key={id} value={id}>
                          {name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Expected difficulty
                  <select
                    value={draft.difficulty}
                    onChange={(e) => patch({ difficulty: e.target.value as Draft['difficulty'] })}
                  >
                    {['easy', 'medium', 'hard', 'mixed'].map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                Task ID
                <input
                  readOnly={!!editing}
                  value={draft.slug}
                  maxLength={120}
                  placeholder="Generated from the title"
                  onChange={(e) => patch({ slug: e.target.value })}
                />
              </label>
              <label>
                Why this task exists
                <textarea
                  rows={2}
                  value={draft.motivation}
                  maxLength={12000}
                  placeholder="A real bug, issue link, or behavior worth testing. Required before export."
                  onChange={(e) => patch({ motivation: e.target.value })}
                />
              </label>
            </details>
          </section>
          {native && !editing && (
            <section className="panel form-section">
              <h2>Simulator scenario</h2>
              <p className="form-intro">
                Start with an existing app and UI flow. Adapt the prompt, verifier, and reference
                automation for your task.
              </p>
              {library.error && <Notice tone="error">{library.error.message}</Notice>}
              <label>
                Start from
                <select
                  value={draft.simulator?.template ?? ''}
                  onChange={(e) => {
                    if (e.target.value) template.mutate(e.target.value)
                  }}
                >
                  <option value="">
                    {library.isPending ? 'Loading scenarios…' : 'Choose a simulator task'}
                  </option>
                  {library.data?.tasks
                    .filter((task) => task.family === 'simbench')
                    .map((task) => (
                      <option key={task.id} value={task.id}>
                        {task.title}
                        {task.held ? ' · On hold' : ''}
                      </option>
                    ))}
                </select>
              </label>
              {draft.simulator && (
                <>
                  <label>
                    Scenario type
                    <select
                      value={draft.simulator.tier}
                      onChange={(e) =>
                        patch({ simulator: { ...draft.simulator!, tier: e.target.value } })
                      }
                    >
                      {Object.entries(simulatorTiers).map(([id, label]) => (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="field-hint">
                    Uses a disposable iOS simulator. The verifier checks app state and UI events;
                    calibration requires macOS and Xcode.
                  </p>
                  <h3>Check the result</h3>
                  <p className="form-intro">
                    Update verify.py to describe success. Keep the UI event checks so writing app
                    data directly cannot pass.
                  </p>
                  <CodeFiles draft={draft} area="checks" patch={patch} />
                  <h3>Reference UI automation</h3>
                  <p className="form-intro">
                    Update oracle.py to complete the task through the simulator. It must satisfy the
                    verifier during calibration.
                  </p>
                  <CodeFiles draft={draft} area="reference" patch={patch} />
                  <details className="authoring-settings">
                    <summary>App source</summary>
                    <CodeFiles draft={draft} area="environment" patch={patch} />
                  </details>
                </>
              )}
            </section>
          )}
          {!native && (
            <section className="panel form-section" aria-labelledby="grading-heading">
              <div className="authoring-section-heading">
                <h2 id="grading-heading">How to grade it</h2>
                <Badge>RewardKit</Badge>
              </div>
              <p className="form-intro">
                {gradingLocked
                  ? 'Edit the requirements below. This task also has a policy or native verifier, which is preserved when you save.'
                  : 'Add a check for each requirement. You can mix tests, file checks, and AI review.'}
              </p>
              <div className="criteria-editor">
                {draft.criteria.map((c, i) => (
                  <div className="criterion-editor" key={c.id}>
                    <div className="criterion-editor-top">
                      <strong>Check {i + 1}</strong>
                      <Button
                        disabled={gradingLocked}
                        variant="quiet"
                        aria-label={`Remove check ${i + 1}`}
                        onClick={() =>
                          patch({
                            criteria: draft.criteria.filter((_, j) => j !== i),
                            mustFail: draft.mustFail.filter((id) => id !== c.id),
                            baselineMustFail: draft.baselineMustFail.filter((id) => id !== c.id),
                          })
                        }
                      >
                        Remove
                      </Button>
                    </div>
                    <label>
                      Requirement
                      <textarea
                        rows={2}
                        value={c.description}
                        maxLength={8000}
                        placeholder="The screen returns to its previous scroll position after navigating back."
                        onChange={(e) => updateCriterion(i, { description: e.target.value })}
                      />
                    </label>
                    {editing?.policyCriteria.includes(c.id) ? (
                      <div className="field-hint">Checked by the existing policy contract.</div>
                    ) : (
                      <label>
                        Check with
                        <select
                          disabled={gradingLocked}
                          value={c.grading.kind}
                          onChange={(e) => chooseGrader(i, e.target.value as GraderKind)}
                        >
                          {graderGroups.map((group) => (
                            <optgroup key={group} label={group}>
                              {graderOptions
                                .filter((grader) => grader.group === group)
                                .map((grader) => (
                                  <option key={grader.kind} value={grader.kind}>
                                    {grader.label}
                                  </option>
                                ))}
                            </optgroup>
                          ))}
                        </select>
                        <span className="field-hint">{graders[c.grading.kind].description}</span>
                      </label>
                    )}
                    <GraderFields
                      kind={c.grading.kind}
                      config={c.grading.config}
                      onChange={(config) =>
                        updateCriterion(i, { grading: { ...c.grading, config } })
                      }
                    />
                    <CheckScoring
                      criterion={c}
                      locked={gradingLocked}
                      weightedSum={draft.scoring.aggregation === 'weighted-sum'}
                      update={(change) => updateCriterion(i, change)}
                    />
                  </div>
                ))}
              </div>
              <Button
                disabled={gradingLocked || draft.criteria.length >= 24}
                onClick={() => {
                  const id = nextCheckId(draft.criteria)
                  patch({
                    criteria: [
                      ...draft.criteria,
                      {
                        id,
                        name: id,
                        description: '',
                        weight: 1,
                        grading: { kind: 'ai-review', config: {} },
                      },
                    ],
                    ...(!draft.criteria.length ? { mustFail: [id], baselineMustFail: [id] } : {}),
                  })
                }}
              >
                <PlusIcon />
                Add check
              </Button>
              {!gradingLocked && (
                <details className="authoring-settings">
                  <summary>Combine scores</summary>
                  <label>
                    Scoring method
                    <select
                      disabled={gradingLocked}
                      value={draft.scoring.aggregation}
                      onChange={(e) =>
                        patch({
                          scoring: {
                            ...draft.scoring,
                            aggregation: e.target.value as Draft['scoring']['aggregation'],
                          },
                        })
                      }
                    >
                      {Object.entries(aggregations).map(([id, rule]) => (
                        <option key={id} value={id}>
                          {rule.label}
                        </option>
                      ))}
                    </select>
                    <span className="field-hint">
                      {aggregations[draft.scoring.aggregation].description}
                    </span>
                  </label>
                  {draft.scoring.aggregation === 'threshold' && (
                    <label>
                      Passing threshold
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.05}
                        value={draft.scoring.threshold}
                        onChange={(e) =>
                          patch({
                            scoring: { ...draft.scoring, threshold: Number(e.target.value) },
                          })
                        }
                      />
                    </label>
                  )}
                </details>
              )}
            </section>
          )}
          {!native && (
            <details className="panel form-section authoring-disclosure">
              <summary>
                <span>
                  <CodeIcon />
                  <strong>Starting code</strong>
                </span>
                <Badge>{draft.files.filter((f) => f.area === 'environment').length} files</Badge>
              </summary>
              <p className="form-intro">
                The workspace the agent receives. Include the bug and everything needed to reproduce
                it.
              </p>
              <CodeFiles draft={draft} area="environment" patch={patch} />
            </details>
          )}
          {hasTests && (
            <details className="panel form-section authoring-disclosure" open>
              <summary>
                <span>
                  <FileIcon />
                  <strong>Test files</strong>
                </span>
                <Badge>Verifier only</Badge>
              </summary>
              <p className="form-intro">
                Add assertions or trajectory fixtures here. These files stay outside the agent's
                workspace. Generated script placeholders fail until you replace them.
              </p>
              <CodeFiles draft={draft} area="checks" patch={patch} />
            </details>
          )}
          {!native && (
            <details className="panel form-section authoring-disclosure">
              <summary>
                <span>
                  <ShieldIcon />
                  <strong>Examples to test your grader</strong>
                </span>
                <Badge>{editing ? 'Calibration' : 'Before export'}</Badge>
              </summary>
              <p className="form-intro">
                A correct answer should pass. A plausible wrong answer should fail the check for the
                bug it leaves behind.
              </p>
              <h3 className="control-heading">
                <CheckCircleIcon className="green" />
                Correct answer
              </h3>
              <CodeFiles draft={draft} area="reference" patch={patch} />
              <h3 className="control-heading">
                <CodeIcon className="amber" />
                Plausible wrong answer
              </h3>
              <CodeFiles draft={draft} area="distractor" patch={patch} />
              <div className="must-fail">
                <h3>Checks the wrong answer must fail</h3>
                {draft.criteria.map((c, i) => (
                  <label key={c.id}>
                    <input
                      type="checkbox"
                      checked={draft.mustFail.includes(c.id)}
                      onChange={(e) =>
                        patch({
                          mustFail: e.target.checked
                            ? [...draft.mustFail, c.id]
                            : draft.mustFail.filter((id) => id !== c.id),
                        })
                      }
                    />
                    {c.description || `Check ${i + 1}`}
                  </label>
                ))}
                <h3>Checks the unchanged behavior must fail</h3>
                <p className="field-hint">
                  Calibration adds a comment to the starting code. That alone must not fix the bug.
                </p>
                {draft.criteria.map((c, i) => (
                  <label key={c.id}>
                    <input
                      type="checkbox"
                      checked={draft.baselineMustFail.includes(c.id)}
                      onChange={(e) =>
                        patch({
                          baselineMustFail: e.target.checked
                            ? [...draft.baselineMustFail, c.id]
                            : draft.baselineMustFail.filter((id) => id !== c.id),
                        })
                      }
                    />
                    {c.description || `Check ${i + 1}`}
                  </label>
                ))}
              </div>
            </details>
          )}
          {!editing && (
            <details className="panel form-section authoring-disclosure">
              <summary>
                <span>
                  <FileIcon />
                  <strong>Export to Harbor</strong>
                </span>
                <Badge>{issues.length ? `${issues.length} to complete` : 'Ready to export'}</Badge>
              </summary>
              <p className="form-intro">
                Save a task folder for review and calibration. Exporting does not run the grader.
              </p>
              {issues.length > 0 ? (
                <Notice>
                  <strong>Before exporting</strong>
                  <ul>
                    {issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </Notice>
              ) : (
                <Notice tone="success">
                  The required files and checks are present. Your grader still needs calibration.
                </Notice>
              )}
              <Button
                variant="primary"
                disabled={
                  issues.length > 0 || (!dirty && exportMutation.data?.revision === draft.revision)
                }
                busy={exportMutation.isPending}
                onClick={() => exportMutation.mutate()}
              >
                <FileIcon />
                Save & export task
              </Button>
              {exportMutation.error && <Notice tone="error">{exportMutation.error.message}</Notice>}
              {exportMutation.data && (
                <Notice tone="success">
                  Exported {exportMutation.data.files.length} files to{' '}
                  <code>{exportMutation.data.path}</code>. Review and calibrate this task before
                  adding it to the library.
                </Notice>
              )}
            </details>
          )}
          <div className="authoring-save-row">
            <p>
              {editing
                ? 'Changes are saved to this task in the library.'
                : "Save at any point. Finish the code and examples when you're ready."}
            </p>
            <Button
              variant="primary"
              busy={save.isPending}
              disabled={busy || (!dirty && (draft.revision > 0 || !!editing))}
              onClick={() => save.mutate()}
            >
              <SaveIcon />
              {saveLabel}
            </Button>
          </div>
        </div>
        {!native && (
          <aside className="authoring-summary panel">
            <h3>Your evaluation</h3>
            <dl className="detail-list">
              <div>
                <dt>Checks</dt>
                <dd>{draft.criteria.length}</dd>
              </div>
              <div>
                <dt>Scoring</dt>
                <dd>
                  {editing?.policyCriteria.length
                    ? 'All required checks'
                    : aggregations[draft.scoring.aggregation].label}
                </dd>
              </div>
              <div>
                <dt>Judge usage</dt>
                <dd>{hasJudge ? 'AI review selected' : 'No model calls'}</dd>
              </div>
            </dl>
            <p>
              {editing?.policyCriteria.length
                ? 'Every required check must pass for this task to score 1.'
                : aggregations[draft.scoring.aggregation].description}
            </p>
            {draft.sourceTask && !editing && (
              <p className="field-hint">Copied from {draft.sourceTask}.</p>
            )}
          </aside>
        )}
      </fieldset>
    </>
  )
}

function LeaveDialog({ onStay, onLeave }: { onStay: () => void; onLeave: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])
  return (
    <dialog
      ref={ref}
      className="leave-dialog"
      aria-labelledby="leave-title"
      onCancel={(event) => {
        event.preventDefault()
        onStay()
      }}
    >
      <h2 id="leave-title">Keep your changes?</h2>
      <p>This draft has unsaved edits.</p>
      <div className="actions">
        <Button autoFocus onClick={onStay}>
          Keep editing
        </Button>
        <Button variant="danger" onClick={onLeave}>
          Discard and leave
        </Button>
      </div>
    </dialog>
  )
}

function CodeFiles({
  draft,
  area,
  patch,
}: {
  draft: Draft
  area: Draft['files'][number]['area']
  patch: (value: Partial<Draft>) => void
}) {
  const [selected, setSelected] = useState(0)
  const [newPath, setNewPath] = useState('')
  const [error, setError] = useState('')
  const files = draft.files.filter((f) => f.area === area)
  const active = files[Math.min(selected, files.length - 1)]
  const add = () => {
    const parsed = filePathSchema.safeParse(newPath)
    if (!parsed.success) return setError(parsed.error.issues[0].message)
    if (files.some((f) => f.path === newPath))
      return setError('A file with this path already exists.')
    patch({ files: [...draft.files, { area, path: newPath, content: '' }] })
    setSelected(files.length)
    setNewPath('')
    setError('')
  }
  return (
    <div className="code-editor">
      <div className="code-tabs">
        {files.map((file, i) => (
          <button
            type="button"
            key={file.path}
            className={file === active ? 'active' : ''}
            onClick={() => setSelected(i)}
          >
            <FileIcon />
            {file.path}
          </button>
        ))}
      </div>
      {active && (
        <>
          <textarea
            aria-label={`${area} ${active.path} source code`}
            spellCheck={false}
            className="source-input"
            value={active.content}
            placeholder={
              area === 'reference'
                ? 'Write a correct implementation…'
                : area === 'checks'
                  ? 'Write assertions against the submitted code…'
                  : area === 'environment'
                    ? 'Write the starting code…'
                    : 'Write a plausible wrong implementation…'
            }
            onChange={(e) =>
              patch({
                files: draft.files.map((file) =>
                  file === active ? { ...file, content: e.target.value } : file,
                ),
              })
            }
          />
          <div className="code-footer">
            <span>
              {active.content.split('\n').length} lines · {area}
            </span>
            <Button
              variant="quiet"
              onClick={() => {
                patch({ files: draft.files.filter((f) => f !== active) })
                setSelected(0)
              }}
            >
              Remove file
            </Button>
          </div>
        </>
      )}
      <div className="add-file">
        <input
          aria-label={`New ${area} file path`}
          placeholder={area === 'checks' ? 'check.cjs' : 'path/to/file.tsx'}
          value={newPath}
          onChange={(e) => setNewPath(e.target.value)}
        />
        <Button onClick={add}>
          <PlusIcon />
          Add file
        </Button>
      </div>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
