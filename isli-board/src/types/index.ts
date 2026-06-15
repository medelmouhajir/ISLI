export interface Agent {
  id: string
  name: string
  description: string | null
  persona: string | null
  picture: string | null
  status: string
  model_provider: string | null
  model_id: string | null
  channels: string[]
  skills: string[]
  config: Record<string, unknown>
  token_budget: number | null
  turn_token_cap: number | null
  token_used: number
  max_retries: number
  fallback_agent_id: string | null
  known_agent_ids: string[]
  heartbeat_at: string | null
  created_at: string
  updated_at: string
  has_api_key: boolean
  api_key_mask: string | null
  api_key?: string | null
  deleted_at?: string | null
  model_routing_enabled: boolean
  secondary_models: Array<{
    provider: string
    model_id: string
    label?: string
    description?: string
    cost_tier?: string
  }>
}

export interface PermittedModel {
  id: number
  model_id: string
  name: string | null
  enabled: boolean
  created_at: string
}

export interface ProviderSettings {
  provider: string
  enabled: boolean
  has_api_key: boolean
  api_key_mask: string | null
  api_key?: string | null
  api_base?: string | null
  models: PermittedModel[]
}

export interface TaskAttachment {
  name: string
  path: string
  size_bytes: number
  attached_by: string
  attached_at: string
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
  parent_task_id: string | null
  depth: number
  tags: string[]
  scheduled_at: string | null
  cron_expression: string | null
  last_triggered_at: string | null
  attachments: TaskAttachment[]
  retain_attachments: boolean
}

export interface ComponentPayload {
  component_type:
    | 'table'
    | 'card'
    | 'button_group'
    | 'comparison_table'
    | 'form'
    | 'json_viewer'
    | 'status_timeline'
    | 'metric_grid'
  props: Record<string, unknown>
  action_id?: string
  text_fallback?: string
}

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'action'
  content: string
  timestamp: string
  action_id?: string
  action_type?: string
  payload?: Record<string, unknown>
  components?: ComponentPayload[]
  audio_url?: string
}

export interface StreamingEvent {
  event_type: string
  data: Record<string, unknown>
  timestamp: string
}

export interface ToolCallEvent {
  tool: string
  status: 'started' | 'done'
  result_summary?: string
  duration_ms?: number
}

export interface ProcessTraceEvent {
  event_type: string
  data: Record<string, unknown>
  timestamp: string
}

export interface Session {
  id: string
  agent_id: string
  user_id: string | null
  channel: string | null
  messages: Message[]
  token_count: number
  status: string // 'ready' | 'pending_context' | 'processing_context' | 'agent_processing' | 'context_failed' | 'closed'
  created_at: string
  last_activity_at: string | null
  journal?: string | null
  journal_updated_at?: string | null
  session_metadata?: Record<string, unknown> | null
}

export interface SessionHistory {
  session_id: string
  agent_id: string
  user_id: string | null
  channel: string | null
  all_messages: Message[]
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

export interface CostHistoryDay {
  date: string
  cost_usd: number
  input_tokens: number
  output_tokens: number
}

export interface CostByTier {
  tier: string
  cost_usd: number
  turns: number
}

export interface BudgetStatus {
  scope: string
  scope_id: string
  monthly_token_cap: number | null
  monthly_usd_cap: number | null
  token_used: number
  usd_used: number
  alert_threshold_pct: number
  slack_webhook_url: string | null
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

export interface SystemSetting {
  key: string
  scope: string
  value: unknown
  description: string | null
  updated_at: string
}

export interface SkillMetadata {
  name: string
  description: string
  type: string
  category: string
  url: string | null
  status: string | null
  last_probe_status: string | null
  last_probe_at: string | null
  version: string | null
  author: string | null
  tools: Record<string, unknown>[]
  // Versioning fields
  source_url: string | null
  source_ref: string | null
  installed_commit_sha: string | null
  latest_commit_sha: string | null
  latest_version: string | null
  update_policy: string
  changelog: Array<{ version: string; date: string; message: string }>
  last_checked_at: string | null
  previous_version: string | null
  previous_commit_sha: string | null
  previous_image_tag: string | null
}

export interface PromptsOut {
  keeper: Record<string, string | Record<string, string>>
  agent: {
    system_prompt_template: string
    tool_descriptions: Record<string, string>
  }
  core: {
    help_text: string
    context_inject_task_desc: string
    prompt_injection_markers: string[]
  }
  last_modified: string
  keeper_reloaded: boolean
  keeper_error?: string | null
}

export interface PromptsUpdate {
  keeper?: Record<string, string | Record<string, string>>
  agent?: {
    system_prompt_template?: string
    tool_descriptions?: Record<string, string>
  }
  core?: {
    help_text?: string
    context_inject_task_desc?: string
    prompt_injection_markers?: string[]
  }
  last_modified: string
}

export interface NotificationItem {
  id: string
  user_id: string
  event_type: string
  category: 'critical' | 'high' | 'normal' | 'low'
  title: string
  body: string | null
  payload: Record<string, unknown>
  read_at: string | null
  dismissed_at: string | null
  created_at: string
  agent_id: string | null
  task_id: string | null
  session_id: string | null
}

export interface NotificationListResponse {
  items: NotificationItem[]
  total: number
  unread_count: number
}

export interface NotificationPreferences {
  user_id: string
  global_enabled: boolean
  quiet_hours_enabled: boolean
  quiet_hours_start: string | null
  quiet_hours_end: string | null
  timezone: string
  quiet_hours_exceptions: string[]
  categories: Record<string, unknown>
}

