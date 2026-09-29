import type { Draft } from '../lib/schema'
import { graders, type GraderKind } from '../lib/grading'

type Criterion = Draft['criteria'][number]

export function GraderFields({
  kind,
  config,
  onChange,
}: {
  kind: GraderKind
  config: Record<string, string>
  onChange: (config: Record<string, string>) => void
}) {
  return graders[kind].fields.map((field) => {
    const props = {
      value: config[field.key] ?? field.default ?? '',
      placeholder: field.placeholder,
      maxLength: ['path', 'script', 'python'].includes(field.type) ? 200 : 8000,
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        onChange({ ...config, [field.key]: event.target.value }),
    }
    return (
      <label key={field.key}>
        {field.label}
        {field.optional && <span className="field-hint">Optional</span>}
        {['multiline', 'json'].includes(field.type) ? (
          <textarea rows={3} {...props} />
        ) : (
          <input
            {...props}
            type={
              ['number', 'integer'].includes(field.type)
                ? 'number'
                : field.type === 'url'
                  ? 'url'
                  : 'text'
            }
            min={field.min}
            max={field.max}
            step={field.type === 'integer' ? 1 : 'any'}
          />
        )}
        {['script', 'python'].includes(field.type) && (
          <span className="field-hint">
            Edit this verifier-only file in Test files below.{' '}
            {field.type === 'script'
              ? 'Receives the submission path as its first argument; exit 0 to pass (30-second timeout).'
              : 'Use a RewardKit @criterion factory with a workspace argument.'}
          </span>
        )}
        {field.type === 'trajectory' && (
          <span className="field-hint">
            The export transfers the Harbor agent trajectory to the verifier. A relative path reads
            a fixture from Test files. Trajectory evidence does not prove app behavior.
          </span>
        )}
      </label>
    )
  })
}

export function CheckScoring({
  criterion: c,
  locked,
  weightedSum,
  update,
}: {
  criterion: Criterion
  locked: boolean
  weightedSum: boolean
  update: (change: Partial<Criterion>) => void
}) {
  return (
    <details className="check-settings">
      <summary>Scoring & weight</summary>
      {c.grading.kind === 'ai-review' ? (
        <>
          <label>
            Score format
            <select
              disabled={locked}
              value={c.type ?? 'binary'}
              onChange={(e) => update({ type: e.target.value as Criterion['type'] })}
            >
              <option value="binary">Pass / fail</option>
              <option value="likert">Rating scale</option>
              <option value="numeric">Numeric range</option>
            </select>
          </label>
          {c.type === 'likert' && (
            <label>
              Scale points
              <input
                disabled={locked}
                type="number"
                min={2}
                max={100}
                value={c.points ?? 5}
                onChange={(e) => update({ points: Number(e.target.value) })}
              />
            </label>
          )}
          {c.type === 'numeric' && (
            <div className="form-grid">
              <label>
                Minimum
                <input
                  disabled={locked}
                  type="number"
                  step="any"
                  value={c.min ?? 0}
                  onChange={(e) => update({ min: Number(e.target.value) })}
                />
              </label>
              <label>
                Maximum
                <input
                  disabled={locked}
                  type="number"
                  step="any"
                  value={c.max ?? 1}
                  onChange={(e) => update({ max: Number(e.target.value) })}
                />
              </label>
            </div>
          )}
        </>
      ) : (
        <p className="field-hint">
          {graders[c.grading.kind].score === 'continuous'
            ? 'This check returns a score from 0 to 1.'
            : 'This check returns pass or fail.'}
        </p>
      )}
      <label>
        Weight
        <input
          type="number"
          min={weightedSum ? -100 : 0}
          max={100}
          step="any"
          value={c.weight}
          onChange={(e) => update({ weight: Number(e.target.value) })}
        />
      </label>
      <label className="check-option">
        <input
          disabled={locked}
          type="checkbox"
          checked={c.negate ?? false}
          onChange={(e) => update({ negate: e.target.checked })}
        />
        Invert score (1 − score)
      </label>
      <label className="check-option">
        <input
          disabled={locked}
          type="checkbox"
          checked={c.optional ?? false}
          onChange={(e) => update({ optional: e.target.checked })}
        />
        Optional for “All required checks pass”
      </label>
      <p className="field-hint">{c.id} · equal weights by default</p>
    </details>
  )
}
