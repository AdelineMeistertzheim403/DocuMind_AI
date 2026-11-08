import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../services/api'
import type { AnalyzeOptions } from '../types/api'

export const listKey = ['documents'] as const
export function useDocuments(offset = 0, limit = 12) {
  return useQuery({ queryKey: [...listKey, offset, limit], queryFn: ({ signal }) => api.documents(offset, limit, signal) })
}
export function useDocument(id: string) {
  return useQuery({ queryKey: ['document', id], queryFn: ({ signal }) => api.document(id, signal), enabled: !!id })
}
export function useAnalysis(id: string) {
  return useQuery({ queryKey: ['analysis', id], queryFn: ({ signal }) => api.analysis(id, signal), enabled: !!id,
    retry: (count, error) => !(error instanceof ApiError && [401, 404, 422].includes(error.status)) && count < 1,
  })
}
export function useUpload() {
  const client = useQueryClient()
  return useMutation({ mutationFn: api.upload, onSuccess: () => client.invalidateQueries({ queryKey: listKey }) })
}
export function useRemove() {
  const client = useQueryClient()
  return useMutation({ mutationFn: api.remove, onSuccess: async (_, id) => {
    client.removeQueries({ queryKey: ['document', id] }); client.removeQueries({ queryKey: ['analysis', id] })
    await client.invalidateQueries({ queryKey: listKey })
  } })
}
export function useAnalyze(id: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: (options: Partial<AnalyzeOptions>) => api.analyze(id, options),
    onSuccess: result => { client.setQueryData(['analysis', id], result) },
  })
}
