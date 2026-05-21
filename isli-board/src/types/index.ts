export interface Agent {
  id: string
  name: string
  description: string | null
  persona: string | null
  status: string
  model_provider: string | null
  model_id: string | null
  channels: string[]
  skills: string[]
  config: Record<string, unknown>
  token_budget: number | null
  token_used: number
  max_retries: number
  fallback_agent_id: string | null
  heartbeat_at: string | null
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  title: string
  description: string | null
  status: string
  priority: number
  agent_id: string | null
  created_by: string
  created_at: string
  input: string
  output: string | null
  channel: string | null
  depth: number
  tags: string[]
  scheduled_at: string | null
}

export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

export interface Session {
  id: string
  agent_id: string
  user_id: string | null
  channel: string | null
  messages: Message[]
  token_count: number
  status: string // 'ready' | 'pending_context' | 'processing_context' | 'context_failed' | 'closed'
  created_at: string
  last_activity_at: string | null
}

export interface CostDashboard {
  total_agents: number
  total_tasks: number
  total_cost_usd: number
  avg_cost_per_agent: number
  agent_costs: { agent_id: string; cost_usd: number; tokens: number }[]
}

export interface KeeperInference {
  timestamp: string
  agent_id: string
  endpoint: string
  model: string
  latency_ms: number
  prompt?: string
  completion?: string
  prompt_preview: string
  completion_preview: string
  tokens_in: number | null
  tokens_out: number | null
  status: string
  error: string | null
}

export interface KeeperIdentity {
  backend: string
  ollama_host: string
  default_gen_model: string
  default_embed_model: string
  model_info: {
    parameter_size: string | null
    quantization: string | null
    context_length: number | null
    format: string | null
  }
}

export interface KeeperHealth {
  status: string
  uptime_seconds: number
  active_requests: number
  ollama_ps: Record<string, unknown>
}

export interface KeeperStats {
  total_requests: number
  avg_latency_ms: number
  agent_calls: Record<string, Record<string, number>>
  error_counts: Record<string, number>
}

export interface KeeperConfig {
  num_ctx: number
  num_batch: number
  ollama_gen_model: string
  ollama_embed_model: string
}

export interface KeeperDashboard {
  identity: KeeperIdentity
  health: KeeperHealth
  stats: KeeperStats
  recent_inferences: KeeperInference[]
  config: KeeperConfig
}

export interface WorkspaceEntry {
  name: string
  type: 'file' | 'directory'
  size_bytes: number
  modified_at: string
}

export interface WorkspaceListResponse {
  status: string
  entries: WorkspaceEntry[]
}

export interface WorkspaceReadResponse {
  status: string
  content: string
  size_bytes: number
  modified_at: string
  encoding: string
}

