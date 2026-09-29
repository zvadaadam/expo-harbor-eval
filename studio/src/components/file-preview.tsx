import { useQuery } from '@tanstack/react-query'
import { Notice } from './ui'
import type { fileContentSchema } from '../lib/schema'
import type { z } from 'zod'

export function FilePreview({
  queryKey,
  load,
}: {
  queryKey: string[]
  load: () => Promise<z.infer<typeof fileContentSchema>>
}) {
  const result = useQuery({ queryKey, queryFn: load, staleTime: 30_000 })
  if (result.isPending)
    return (
      <div className="file-loading">
        <span className="spinner" />
        Reading file…
      </div>
    )
  if (result.isError) return <Notice tone="error">{result.error.message}</Notice>
  return (
    <>
      {result.data.truncated && (
        <Notice tone="warning">
          Preview limited to the first 200 KB. The original file is unchanged.
        </Notice>
      )}
      {result.data.kind === 'image' ? (
        <img
          className="evidence-image"
          src={result.data.content}
          alt="Screenshot recorded for this attempt"
        />
      ) : (
        <pre className="code-preview" tabIndex={0}>
          <code>{result.data.content || '(empty file)'}</code>
        </pre>
      )}
    </>
  )
}
