import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON, deleteJSON, postFormData } from '@/lib/api'
import type { WorkspaceListResponse, WorkspaceReadResponse } from '@/types'

export function useWorkspaceFiles(agentId: string, path: string = '') {
  return useQuery({
    queryKey: ['workspaces', agentId, 'list', path],
    queryFn: () => getJSON<WorkspaceListResponse>(`/v1/workspaces/${agentId}/list?path=${encodeURIComponent(path)}`),
    staleTime: 10000,
    enabled: !!agentId,
  })
}

export function useReadWorkspaceFile(agentId: string, path: string | null) {
  return useQuery({
    queryKey: ['workspaces', agentId, 'read', path],
    queryFn: () => getJSON<WorkspaceReadResponse>(`/v1/workspaces/${agentId}/read?path=${encodeURIComponent(path!)}`),
    enabled: !!agentId && !!path,
    staleTime: 0,
  })
}

export function useWriteWorkspaceFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ agentId, path, content }: { agentId: string; path: string; content: string }) =>
      postJSON(`/v1/workspaces/${agentId}/write`, { path, content }),
    onSuccess: (_, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces', agentId] })
    },
  })
}

export function useDeleteWorkspaceFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ agentId, path }: { agentId: string; path: string }) =>
      deleteJSON(`/v1/workspaces/${agentId}/delete?path=${encodeURIComponent(path)}`),
    onSuccess: (_, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces', agentId] })
    },
  })
}

export function useUploadWorkspaceFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ agentId, path, file }: { agentId: string; path: string; file: File }) => {
      const formData = new FormData()
      formData.append('file', file)
      return postFormData(`/v1/workspaces/${agentId}/upload?path=${encodeURIComponent(path)}`, formData)
    },
    onSuccess: (_, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces', agentId] })
    },
  })
}

export function useCreateWorkspaceFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ agentId, path }: { agentId: string; path: string }) =>
      postJSON(`/v1/workspaces/${agentId}/mkdir`, { path }),
    onSuccess: (_, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces', agentId] })
    },
  })
}
