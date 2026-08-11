// LLM 配置的本地持久化与请求载荷构建工具。
// 配置以 JSON 形式存入 localStorage（key: fa_llm_config），并兼容旧版 fa_api_key。
// camelCase 为前端内部结构；发送给后端时转换为 snake_case（对齐 Pydantic 模型）。

// localStorage 存储的配置结构（camelCase，前端内部使用）
export interface LLMConfig {
  apiKey: string
  model: string
  baseUrl: string
  thinking: string // "enabled" | "disabled" | ""（空表示未设置，回退后端默认）
}

// 后端 llm_config 请求载荷（camelCase，对齐后端 LLMConfigRequest 模型 baseUrl/apiKey）
export interface LLMConfigPayload {
  model?: string
  baseUrl?: string
  apiKey?: string
  thinking?: string
}

export const FA_LLM_CONFIG_KEY = 'fa_llm_config'
// 多配置管理：profiles 存储 key
export const FA_LLM_PROFILES_KEY = 'fa_llm_profiles'
// 旧版 API Key 的 localStorage key（迁移来源）
const LEGACY_API_KEY_STORAGE = 'fa_api_key'

// Provider 预设：选择后自动填充 model/baseUrl/thinking（静态常量，无后端依赖）
export interface ProviderPreset {
  name: string
  model: string
  baseUrl: string
  thinking: string // "" 表示该预设不展示思考开关（非 DeepSeek 模型）
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { name: 'DeepSeek 官方', model: 'deepseek/deepseek-chat', baseUrl: 'https://api.deepseek.com/v1', thinking: 'enabled' },
  { name: 'OpenAI', model: 'openai/gpt-4o', baseUrl: '', thinking: '' },
  { name: 'Anthropic', model: 'anthropic/claude-sonnet-4-20250514', baseUrl: '', thinking: '' },
  { name: '本地 Ollama', model: 'openai/llama3', baseUrl: 'http://localhost:11434/v1', thinking: '' },
  { name: '自定义', model: '', baseUrl: '', thinking: 'enabled' },
]

export const CUSTOM_PRESET_NAME = '自定义'

// 空配置（首次加载/未配置时的默认值）
export function emptyLlmConfig(): LLMConfig {
  return { apiKey: '', model: '', baseUrl: '', thinking: '' }
}

// 从 localStorage 读取配置。
// 自动迁移：若 fa_llm_config 不存在但旧 key fa_api_key 存在，读取旧值为 apiKey 并清除旧 key。
export function loadLlmConfig(): LLMConfig {
  const raw = localStorage.getItem(FA_LLM_CONFIG_KEY)
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Partial<LLMConfig>
      return {
        apiKey: typeof parsed.apiKey === 'string' ? parsed.apiKey : '',
        model: typeof parsed.model === 'string' ? parsed.model : '',
        baseUrl: typeof parsed.baseUrl === 'string' ? parsed.baseUrl : '',
        thinking: typeof parsed.thinking === 'string' ? parsed.thinking : '',
      }
    } catch {
      // JSON 损坏：继续走迁移/默认分支
    }
  }
  // 迁移：旧 key 存在时，将其值作为 apiKey，写入新 key 并清除旧 key
  const legacy = localStorage.getItem(LEGACY_API_KEY_STORAGE)
  if (legacy) {
    const cfg: LLMConfig = { apiKey: legacy, model: '', baseUrl: '', thinking: '' }
    localStorage.setItem(FA_LLM_CONFIG_KEY, JSON.stringify(cfg))
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
    return cfg
  }
  return emptyLlmConfig()
}

// 保存配置到 localStorage
export function saveLlmConfigToStorage(cfg: LLMConfig): void {
  localStorage.setItem(FA_LLM_CONFIG_KEY, JSON.stringify(cfg))
}

// 构建后端请求载荷（snake_case）。仅在有任意非空字段时返回对象，否则返回 null。
// 与 spec 场景对齐：「请求体 SHALL 包含 llm_config 字段，包含用户配置的非空字段」。
export function buildLlmConfigPayload(cfg: LLMConfig): LLMConfigPayload | null {
  const payload: LLMConfigPayload = {}
  const model = cfg.model.trim()
  const baseUrl = cfg.baseUrl.trim()
  const apiKey = cfg.apiKey.trim()
  if (model) payload.model = model
  if (baseUrl) payload.baseUrl = baseUrl
  if (apiKey) payload.apiKey = apiKey
  // thinking 仅在显式取值 enabled/disabled 时携带（空值回退后端默认）
  if (cfg.thinking === 'enabled' || cfg.thinking === 'disabled') payload.thinking = cfg.thinking
  return Object.keys(payload).length > 0 ? payload : null
}

// 判断模型名是否为 DeepSeek 系列（决定是否展示思考模式开关）
export function isDeepSeekModel(model: string): boolean {
  return model.toLowerCase().includes('deepseek')
}

// 根据当前 model/baseUrl/thinking 匹配预设名；无精确匹配返回"自定义"。
// 用于：用户手动修改输入框后，预设选择器自动切换为"自定义"。
export function matchPreset(cfg: { model: string; baseUrl: string; thinking: string }): string {
  const found = PROVIDER_PRESETS.find(
    (p) =>
      p.name !== CUSTOM_PRESET_NAME &&
      p.model === cfg.model &&
      p.baseUrl === cfg.baseUrl &&
      p.thinking === cfg.thinking,
  )
  return found ? found.name : CUSTOM_PRESET_NAME
}

// 为模型自动发现返回的原始模型名拼接 litellm 前缀。
// 规则（对齐 spec 场景）：
//   1. 原始值已含 '/' → 直接使用（已是 litellm 格式）
//   2. 否则 → 从 baseUrl 域名主体推导前缀（api.deepseek.com → deepseek），拼成 `deepseek/<model>`
//   3. baseUrl 非法或为空 → 返回原始模型名（交由用户手动补全）
export function buildModelWithPrefix(rawModel: string, baseUrl: string): string {
  const model = rawModel.trim()
  if (!model) return model
  if (model.includes('/')) return model
  const trimmedBase = baseUrl.trim()
  if (!trimmedBase) return model
  try {
    const host = new URL(trimmedBase).hostname
    const parts = host.split('.').filter(Boolean)
    // 过滤常见非主体段（api/www/com/cn/org/net/io/ai/dev/co 等），取首个主体段作为前缀
    const insignificant = new Set(['api', 'www', 'com', 'cn', 'org', 'net', 'io', 'ai', 'dev', 'co'])
    const significant = parts.filter((p) => p && !insignificant.has(p.toLowerCase()))
    const prefix = significant[0] || parts[0] || 'openai'
    return `${prefix.toLowerCase()}/${model}`
  } catch {
    // baseUrl 非法（如缺少协议）时无法推导前缀，返回原始模型名
    return model
  }
}

// ── 多配置管理（profiles）── add-custom-llm-api Decision 10（方案 A）──
// 多套命名 LLM 配置，存浏览器 localStorage（key: fa_llm_profiles），后端不存储。

// 单个 profile（命名配置）
export interface LLMProfile {
  id: string        // 唯一 ID（Date.now().toString()）
  name: string      // 用户命名，如「DeepSeek 办公」
  config: LLMConfig // { model, baseUrl, apiKey, thinking }
}

// localStorage 存储结构
export interface ProfileStore {
  profiles: LLMProfile[]
  activeId: string  // 当前激活 profile 的 id（空表示无激活，回退默认配置）
}

// 空的 profile store（首次加载/未配置时）
function emptyProfileStore(): ProfileStore {
  return { profiles: [], activeId: '' }
}

// 从 localStorage 读取 profiles。
// 自动迁移：若 fa_llm_profiles 不存在/为空但旧 key fa_llm_config 或 fa_api_key 存在，
// 迁移为第一个 profile（名称「旧配置」）并激活，迁移后清除旧 key。
export function loadProfiles(): ProfileStore {
  const raw = localStorage.getItem(FA_LLM_PROFILES_KEY)
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Partial<ProfileStore>
      const profiles = Array.isArray(parsed.profiles) ? parsed.profiles.filter(isValidProfile) : []
      const activeId = typeof parsed.activeId === 'string' ? parsed.activeId : ''
      return { profiles, activeId }
    } catch {
      // JSON 损坏：继续走迁移/默认分支
    }
  }
  // 迁移：fa_llm_profiles 不存在时尝试从旧 key 迁移
  const legacyCfg = loadLlmConfig()
  const hasLegacy = legacyCfg.apiKey || legacyCfg.model || legacyCfg.baseUrl || legacyCfg.thinking
  if (hasLegacy) {
    const store = addProfile(emptyProfileStore(), '旧配置', legacyCfg)
    saveProfiles(store)
    // 迁移后清除旧 key
    localStorage.removeItem(FA_LLM_CONFIG_KEY)
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
    return store
  }
  return emptyProfileStore()
}

// 保存 profiles 到 localStorage
export function saveProfiles(store: ProfileStore): void {
  localStorage.setItem(FA_LLM_PROFILES_KEY, JSON.stringify(store))
}

// 添加新 profile（名称为空时不添加，返回原 store）
export function addProfile(store: ProfileStore, name: string, config: LLMConfig): ProfileStore {
  const trimmedName = name.trim()
  if (!trimmedName) return store
  const profile: LLMProfile = {
    id: Date.now().toString() + Math.random().toString(36).slice(2, 6),
    name: trimmedName,
    config: { ...config },
  }
  return {
    profiles: [...store.profiles, profile],
    activeId: profile.id, // 新增的 profile 自动设为激活
  }
}

// 删除 profile；若删除的是当前激活项，自动激活剩余第一个（无剩余则 activeId 为空）
export function deleteProfile(store: ProfileStore, id: string): ProfileStore {
  const profiles = store.profiles.filter((p) => p.id !== id)
  let activeId = store.activeId
  if (id === store.activeId) {
    activeId = profiles.length > 0 ? profiles[0].id : ''
  }
  return { profiles, activeId }
}

// 切换激活 profile（id 不存在时保持不变）
export function activateProfile(store: ProfileStore, id: string): ProfileStore {
  const exists = store.profiles.some((p) => p.id === id)
  if (!exists) return store
  return { ...store, activeId: id }
}

// 获取激活 profile 的 config；无 profile 或 activeId 无效时返回空配置或第一个 profile
export function getActiveConfig(store: ProfileStore): LLMConfig {
  if (store.profiles.length === 0) return emptyLlmConfig()
  const active = store.profiles.find((p) => p.id === store.activeId)
  if (active) return active.config
  // activeId 无效时回退到第一个 profile
  return store.profiles[0].config
}

// 获取激活 profile 的显示名称；无 profile 时返回「未配置」
export function getActiveProfileName(store: ProfileStore): string {
  if (store.profiles.length === 0) return '未配置'
  const active = store.profiles.find((p) => p.id === store.activeId)
  if (active) return active.name
  return store.profiles[0].name
}

// 类型守卫：检查对象是否为有效的 LLMProfile
function isValidProfile(obj: unknown): obj is LLMProfile {
  if (typeof obj !== 'object' || obj === null) return false
  const p = obj as Record<string, unknown>
  return typeof p.id === 'string' && typeof p.name === 'string' && typeof p.config === 'object'
}
