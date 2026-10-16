import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE || '/api/v1'

// ── 带拦截器的 axios 实例（所有 API 函数必须用 api，不能用全局 axios）───
// 原先各函数误用全局 axios，导致 token 拦截器不生效 → 需认证接口全部 401
const api = axios.create({ baseURL: BASE_URL, timeout: 30000, withCredentials: true })

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

// ── 401 自动刷新续期 ────────────────────────────────────────────
// access token 30 分钟过期；收到 401 时先用 refresh_token 静默续期并重放原请求，
// 只有续期也失败（refresh 过期/失效）才登出跳登录页。避免用户停留超 30 分钟被强制登出。
let isRefreshing = false
let pendingQueue: Array<(token: string | null) => void> = []

async function refreshAccessToken(): Promise<string | null> {
  try {
    // 用独立 axios（不经本 api 实例，避免拦截器递归）。
    const resp = await axios.post<ApiResp<{ access_token: string }>>(
      `${BASE_URL}/auth/refresh`,
      {},
      { withCredentials: true }
    )
    const data = resp.data
    if (data.code !== 200 || !data.data?.access_token) return null
    localStorage.setItem('token', data.data.access_token)
    return data.data.access_token
  } catch {
    return null
  }
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const { config, response } = err
    // 仅对 401、且非 refresh 请求本身、且未重试过时尝试用 HttpOnly Cookie 续期
    if (
      response?.status === 401 &&
      config &&
      !config._retry &&
      !String(config.url || '').includes('/auth/refresh')
    ) {
      // 多个并发 401：共享同一次刷新，串行重放
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push((token) => {
            if (token) {
              config.headers = config.headers || {}
              config.headers.Authorization = `Bearer ${token}`
              config._retry = true
              resolve(api(config))
            } else {
              reject(err)
            }
          })
        })
      }

      isRefreshing = true
      config._retry = true
      try {
        const newToken = await refreshAccessToken()
        // 唤醒排队请求
        pendingQueue.forEach((fn) => fn(newToken))
        pendingQueue = []
        if (newToken) {
          config.headers = config.headers || {}
          config.headers.Authorization = `Bearer ${newToken}`
          return api(config)
        }
      } finally {
        isRefreshing = false
      }
    }

    // 刷新失败 / 无刷新令牌 / 401 重试仍失败 → 登出跳登录
    if (response?.status === 401) {
      localStorage.removeItem('token')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export interface ApiResp<T = any> {
  code: number
  message: string
  data: T
}

async function unwrap<T>(p: Promise<{ data: ApiResp<T> }>): Promise<T> {
  const { data } = await p
  // 200=查询/更新/删除成功，201=创建成功，两者都视为成功
  if (data.code !== 200 && data.code !== 201) throw new Error(data.message || '请求失败')
  return data.data
}

// ── 类型定义 ────────────────────────────────────────────
export interface UserInfo {
  id: number
  username: string
  real_name?: string
  email?: string
  phone?: string
  avatar?: string
  is_superuser: boolean
  roles: string[]  // role_code 列表（供前端 RBAC 菜单判断）
}

export interface MeInfo extends UserInfo {
  status: string
  organization_id?: number
  permissions: string[]
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface UserItem {
  id: number
  username: string
  real_name?: string
  email?: string
  phone?: string
  avatar?: string
  status: string
  is_superuser: boolean
  organization_id?: number
  roles: string[]
  last_login_time?: string
  login_count?: number
  created_at?: string
}

export interface RoleItem {
  id: number
  role_code: string
  role_name: string
  description?: string
  is_system: boolean
}

// ── 认证 ────────────────────────────────────────────────
export const login = (username: string, password: string) =>
  unwrap<LoginResult>(api.post<ApiResp<LoginResult>>('/auth/login', { username, password }))

export const register = (payload: {
  username: string
  password: string
  real_name?: string
  email?: string
  phone?: string
}) => unwrap<LoginResult>(api.post<ApiResp<LoginResult>>('/auth/register', payload))

export const logout = () =>
  unwrap(api.post<ApiResp>('/auth/logout'))

export const getMe = () =>
  unwrap<MeInfo>(api.get<ApiResp<MeInfo>>('/auth/me'))

// ── 用户管理（超管专用） ────────────────────────────────
export const listUsers = (params: {
  page?: number
  page_size?: number
  keyword?: string
  role_code?: string
  status?: string
} = {}) => unwrap<PageData<UserItem>>(api.get<ApiResp<PageData<UserItem>>>('/users', { params }))

export const createUser = (payload: {
  username: string
  password: string
  real_name?: string
  email?: string
  phone?: string
  role_code: string
  organization_id?: number
}) => unwrap<UserItem>(api.post<ApiResp<UserItem>>('/users', payload))

export const updateUser = (id: number, payload: {
  real_name?: string
  email?: string
  phone?: string
  role_code?: string
  organization_id?: number
}) => unwrap<UserItem>(api.put<ApiResp<UserItem>>(`/users/${id}`, payload))

export const toggleUserStatus = (id: number) =>
  unwrap<UserItem>(api.post<ApiResp<UserItem>>(`/users/${id}/toggle-status`))

export const resetUserPassword = (id: number, new_password: string) =>
  unwrap(api.post<ApiResp>(`/users/${id}/reset-password`, { new_password }))

export const deleteUser = (id: number) =>
  unwrap(api.delete<ApiResp>(`/users/${id}`))

export const listRoles = () =>
  unwrap<RoleItem[]>(api.get<ApiResp<RoleItem[]>>('/users/roles/all'))

// ── 人才档案 ────────────────────────────────────────────
export const listTalents = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/talents', { params }))
export const createTalent = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/talents', payload))
export const deleteTalent = (id: number) =>
  unwrap(api.delete<ApiResp>(`/talents/${id}`))
export const batchDeleteTalents = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/talents/batch-delete', { ids }))
export const getTalent = (id: number) =>
  unwrap<any>(api.get<ApiResp<any>>(`/talents/${id}`))
export const updateTalent = (id: number, payload: any) =>
  unwrap<any>(api.put<ApiResp<any>>(`/talents/${id}`, payload))

// ── 简历上传与解析（存 MinIO + 解析 + 自动建档）────────
export const parseResumeFile = (file: File, onProgress?: (pct: number) => void) => {
  const form = new FormData()
  form.append('file', file)
  return unwrap<any>(api.post<ApiResp<any>>('/talents/parse-resume', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
    timeout: 180000,
  }))
}

// ── 批量导入人才（Excel/CSV，存 MinIO + 清洗去重）──────
export const batchImportTalents = (file: File, onProgress?: (pct: number) => void) => {
  const form = new FormData()
  form.append('file', file)
  return unwrap<any>(api.post<ApiResp<any>>('/talents/batch-import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
    timeout: 180000,
  }))
}

// ── 岗位管理 ────────────────────────────────────────────
export const listPositions = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/positions', { params }))
export const createPosition = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/positions', payload))
export const deletePosition = (id: number) =>
  unwrap(api.delete<ApiResp>(`/positions/${id}`))
export const updatePosition = (id: number, payload: any) =>
  unwrap<any>(api.put<ApiResp<any>>(`/positions/${id}`, payload))
export const batchDeletePositions = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/positions/batch-delete', { ids }))
export const listOrganizations = () =>
  unwrap<any[]>(api.get<ApiResp<any[]>>('/positions/organizations'))

// ── 测评管理 ────────────────────────────────────────────
export const listQuestions = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/assessments/questions', { params }))
export const createQuestion = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/assessments/questions', payload))
export const listPapers = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/assessments/papers', { params }))
export const autoGeneratePaper = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/assessments/papers/auto-generate', payload))
export const simulateAnswer = (paperId: number, payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>(`/assessments/papers/${paperId}/simulate`, payload))
export const getPaperQuestions = (paperId: number, includeAnswer = false) =>
  unwrap<any>(api.get<ApiResp<any>>(`/assessments/papers/${paperId}/questions`, { params: { include_answer: includeAnswer } }))
export const gradeRealAnswer = (paperId: number, payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>(`/assessments/papers/${paperId}/grade`, payload))
export const batchDeleteQuestions = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/assessments/questions/batch-delete', { ids }))
export const batchDeletePapers = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/assessments/papers/batch-delete', { ids }))
export const listAssessmentTasks = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/assessments/tasks', { params }))
export const deleteAssessmentTask = (id: number) =>
  unwrap<any>(api.delete<ApiResp<any>>(`/assessments/tasks/${id}`))
export const batchDeleteAssessmentTasks = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/assessments/tasks/batch-delete', { ids }))
export const listAssessmentResults = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/assessments/results', { params }))

// ── 数据看板 ────────────────────────────────────────────
export const dashboardOverview = () =>
  unwrap<any>(api.get<ApiResp<any>>('/dashboard/overview'))
export const dashboardTalentStructure = () =>
  unwrap<any>(api.get<ApiResp<any>>('/dashboard/talent-structure'))
export const dashboardAlerts = () =>
  unwrap<any>(api.get<ApiResp<any>>('/dashboard/alerts'))
export const dashboardSkillDistribution = () =>
  unwrap<any>(api.get<ApiResp<any>>('/dashboard/skill-distribution'))
export const dashboardAssessmentStatistics = () =>
  unwrap<any>(api.get<ApiResp<any>>('/dashboard/assessment-statistics'))
export const dashboardTrainingStatistics = () =>
  unwrap<any>(api.get<ApiResp<any>>('/dashboard/training-statistics'))
export const dashboardMatchingStatistics = () =>
  unwrap<any>(api.get<ApiResp<any>>('/dashboard/matching-statistics'))

// ── 岗位匹配 ────────────────────────────────────────────
export const matchPosition = (positionId: number, topN = 5) =>
  unwrap<any>(api.post<ApiResp<any>>('/matching/match', { position_id: positionId, top_n: topN }))

// ── 知识库 RAG ──────────────────────────────────────────
export const listKnowledgeFiles = (params: any = {}) =>
  unwrap<any>(api.get<ApiResp<any>>('/knowledge/files', { params }))

export const uploadKnowledgeFile = (file: File, onProgress?: (pct: number) => void) => {
  const form = new FormData()
  form.append('file', file)
  return unwrap<any>(api.post<ApiResp<any>>('/knowledge/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
    timeout: 120000,
  }))
}

export const askKnowledge = (question: string, topK = 5) =>
  unwrap<any>(api.post<ApiResp<any>>('/knowledge/qa', { question, top_k: topK }, { timeout: 120000 }))

export const vectorizeKnowledge = (fileId: number) =>
  unwrap<any>(api.post<ApiResp<any>>('/knowledge/vectorize', { file_id: fileId }, { timeout: 120000 }))
export const deleteKnowledgeFile = (fileId: number) =>
  unwrap<any>(api.delete<ApiResp<any>>(`/knowledge/files/${fileId}`))
export const batchDeleteKnowledgeFiles = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/knowledge/files/batch-delete', { ids }))

export const searchKnowledge = (query: string, topK = 5) =>
  unwrap<any>(api.post<ApiResp<any>>('/knowledge/search', { query, top_k: topK }, { timeout: 120000 }))

// ── 培训管理 ────────────────────────────────────────────
export const listCourses = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/training/courses', { params }))
export const listTrainingPlans = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/training/plans', { params }))
export const createCourse = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/courses', payload))
export const deleteCourse = (id: number) =>
  unwrap<any>(api.delete<ApiResp<any>>(`/training/courses/${id}`))
export const batchDeleteCourses = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/courses/batch-delete', { ids }))
export const createTrainingPlan = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/plans', payload))
export const deleteTrainingPlan = (id: number) =>
  unwrap<any>(api.delete<ApiResp<any>>(`/training/plans/${id}`))
export const batchDeleteTrainingPlans = (ids: number[]) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/plans/batch-delete', { ids }))
export const startLearning = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/learning/start', payload))
export const updateLearningProgress = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/learning/progress', payload))
export const startExamination = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/examination/start', payload))
export const submitExamination = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/training/examination/submit', payload))

// ── 岗位匹配（扩展） ────────────────────────────────────
export const listMatchResults = (params: any = {}) =>
  unwrap<PageData<any>>(api.get<ApiResp<PageData<any>>>('/matching/results', { params }))
export const getPositionCandidates = (positionId: number, topN = 10) =>
  unwrap<any>(api.get<ApiResp<any>>(`/matching/positions/${positionId}/candidates`, { params: { top_n: topN } }))

// ── AI 智能体（五大 Agent） ─────────────────────────────
// 注意：后端路由前缀为 /agents（复数），此处必须一致，否则 404
export const agentParseResume = (payload: any) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/parse-resume', payload, { timeout: 120000 }))
export const agentAnalyzeAssessment = (resultId: number) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/analyze-assessment', { result_id: resultId }, { timeout: 120000 }))
export const agentMatchPosition = (positionId: number) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/match-position', { position_id: positionId }, { timeout: 120000 }))
export const agentMatchTalent = (talentId: number) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/match-position', { talent_id: talentId }, { timeout: 120000 }))
export const agentRecommendTraining = (talentId: number, positionId?: number) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/recommend-training', { talent_id: talentId, position_id: positionId }, { timeout: 120000 }))
export const agentDataAnalysis = (analysisType: string, question?: string) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/data-analysis', { analysis_type: analysisType, question }, { timeout: 120000 }))
export const agentNl2sql = (question: string) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/nl2sql', { question }, { timeout: 120000 }))

// Dify 深度报告（异步任务模式：提交→轮询）
// 1) 提交任务，立即返回 task_id
export const agentDifyReportSubmit = (agent: string, inputs: any, timeoutMs = 30000) =>
  unwrap<any>(api.post<ApiResp<any>>('/agents/dify-report', { agent, inputs }, { timeout: timeoutMs }))
// 2) 轮询任务状态，完成后返回 report
export const agentDifyReportQuery = (taskId: string, timeoutMs = 30000) =>
  unwrap<any>(api.get<ApiResp<any>>(`/agents/dify-report/${taskId}`, { timeout: timeoutMs }))

// ── 员工个人自助（/me）─────────────────────────────
export const meOverview = () =>
  unwrap<any>(api.get<ApiResp<any>>('/me'))
export const uploadMyResume = (file: File, onProgress?: (pct: number) => void) => {
  const form = new FormData()
  form.append('file', file)
  return unwrap<any>(api.post<ApiResp<any>>('/me/resume', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
    timeout: 180000,
  }))
}
export const getMyTalent = () =>
  unwrap<any>(api.get<ApiResp<any>>('/me/talent'))
export const getMyRecommendedPaper = () =>
  unwrap<any>(api.get<ApiResp<any>>('/me/recommended-paper'))
export const submitMyAssessment = (paperId: number, answers: any[], durationSeconds = 0) =>
  unwrap<any>(api.post<ApiResp<any>>(`/me/assessment/${paperId}/submit`, { answers, duration_seconds: durationSeconds }, { timeout: 120000 }))
export const runMyAutoAssessment = (paperId: number) =>
  unwrap<any>(api.post<ApiResp<any>>(`/me/assessment/${paperId}/auto-run`, {}, { timeout: 120000 }))
export const getMyAssessmentResults = () =>
  unwrap<any>(api.get<ApiResp<any>>('/me/assessment/results'))
export const getMyMatchingJobs = () =>
  unwrap<any>(api.get<ApiResp<any>>('/me/matching-jobs'))

export default api
