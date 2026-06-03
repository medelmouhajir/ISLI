import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON, deleteJSON } from '@/lib/api'

export interface SharedWorkspace {
  id: string
  name: string
  description: string | null
  owner_id: string
  members: string[]
  quota_bytes: number
  created_at: string
  updated_at: string
}

export function useSharedWorkspaces() {
  return useQuery({
    queryKey: ['shared-workspaces'],
    queryFn: () => getJSON<SharedWorkspace[]>('/v1/shared-workspaces'),
    staleTime: 30000,
  })
}

export function useCreateSharedWorkspace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      name: string
      description?: string
      owner_id: string
      members?: string[]
      quota_bytes?: number
    }) => postJSON<SharedWorkspace>('/v1/shared-workspaces', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shared-workspaces'] })
    },
  })
}

export function useDeleteSharedWorkspace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteJSON(`/v1/shared-workspaces/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shared-workspaces'] })
    },
  })
}

export function useAddWorkspaceMember() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ workspaceId, memberId }: { workspaceId: string; memberId: string }) =>
      postJSON<SharedWorkspace>(`/v1/shared-workspaces/${workspaceId}/members/${memberId}`, {}),
    onSuccess: (_, { workspaceId }) => {
      queryClient.invalidateQueries({ queryKey: ['shared-workspaces'] })
      queryClient.invalidateQueries({ queryKey: ['shared-workspace', workspaceId] })
    },
  })
}

export function useRemoveWorkspaceMember() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ workspaceId, memberId }: { workspaceId: string; memberId: string }) =>
      deleteJSON(`/v1/shared-workspaces/${workspaceId}/members/${memberId}`),
    onSuccess: (_, { workspaceId }) => {
      queryClient.invalidateQueries({ queryKey: ['shared-workspaces'] })
      queryClient.invalidateQueries({ queryKey: ['shared-workspace', workspaceId] })
    },
  })
}
