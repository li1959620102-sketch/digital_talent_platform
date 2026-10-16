import { BrowserRouter, Routes, Route, Navigate, useLocation, Outlet } from 'react-router-dom'
import { Spin } from 'antd'
import { lazy, ReactNode, Suspense } from 'react'
import { AuthProvider, useAuth } from './AuthContext'
import MainLayout from './MainLayout'

// 页面级懒加载：首屏只下载当前路由，避免一次性加载图表、编排器等重模块。
const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const TalentList = lazy(() => import('./pages/TalentList'))
const PositionList = lazy(() => import('./pages/PositionList'))
const AssessmentList = lazy(() => import('./pages/AssessmentList'))
const Training = lazy(() => import('./pages/Training'))
const Matching = lazy(() => import('./pages/Matching'))
const KnowledgeBase = lazy(() => import('./pages/KnowledgeBase'))
const AgentCenter = lazy(() => import('./pages/AgentCenter'))
const SkillsDesigner = lazy(() => import('./pages/SkillsDesigner'))
const UserList = lazy(() => import('./pages/UserList'))
const MyGrowth = lazy(() => import('./pages/MyGrowth'))

/**
 * 全屏加载（应用启动恢复登录态时）
 */
function FullScreenLoading() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Spin size="large" tip="加载中..." />
    </div>
  )
}

/**
 * 登录守卫：未登录跳 /login
 */
function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullScreenLoading />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

/**
 * 角色守卫：无指定角色跳首页（避免白屏）
 */
function RequireRole({ role, children }: { role: string; children: ReactNode }) {
  const { hasRole } = useAuth()
  if (!hasRole(role)) return <Navigate to="/" replace />
  return <>{children}</>
}

/**
 * 管理侧守卫：super_admin / admin / hr 可进人才管理类页面；
 * 普通用户（user）无权看全局数据，自动落到"我的成长"个人工作台。
 */
function RequireStaff({ children }: { children: ReactNode }) {
  const { user, hasRole } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  const isStaff = hasRole('super_admin') || hasRole('admin') || hasRole('hr')
  if (!isStaff) return <Navigate to="/me" replace />
  return <>{children}</>
}

/**
 * 主路由表
 */
function AppRoutes() {
  const { user, loading } = useAuth()

  if (loading) return <FullScreenLoading />

  return (
    <Routes>
      {/* 登录页：已登录访问 /login 自动跳到各自落点（管理侧→看板，普通员工→我的成长） */}
      <Route
        path="/login"
        element={
          user ? (
            user.is_superuser || (user.roles || []).includes('admin') || (user.roles || []).includes('hr')
              ? <Navigate to="/" replace />
              : <Navigate to="/me" replace />
          ) : <Login />
        }
      />

      {/* 所有业务路由统一到 MainLayout + Outlet（单一 Sider 实例，路由切换时 DOM 稳定） */}
      <Route
        element={
          <RequireAuth>
            <MainLayout><Outlet /></MainLayout>
          </RequireAuth>
        }
      >
        {/* 我的成长（员工个人自助工作台）：全员可访问 */}
        <Route path="/me" element={<MyGrowth />} />

        {/* 管理侧：看板/档案/测评/岗位/培训/匹配（需 staff 角色） */}
        <Route
          element={<RequireStaff><Outlet /></RequireStaff>}
        >
          <Route path="/"          element={<Dashboard />} />
          <Route path="/talents"   element={<TalentList />} />
          <Route path="/positions" element={<PositionList />} />
          <Route path="/assessments" element={<AssessmentList />} />
          <Route path="/training"  element={<Training />} />
          <Route path="/matching"  element={<Matching />} />
        </Route>

        {/* 知识库：全员可访问（员工自助查制度/政策） */}
        <Route path="/knowledge" element={<KnowledgeBase />} />

        {/* AI 智能体 / 技能编排：仅 admin 及以上 */}
        <Route
          element={<RequireRole role="admin"><Outlet /></RequireRole>}
        >
          <Route path="/agent"  element={<AgentCenter />} />
          <Route path="/skills" element={<SkillsDesigner />} />
        </Route>

        {/* 用户管理：仅超管 */}
        <Route
          element={<RequireRole role="super_admin"><Outlet /></RequireRole>}
        >
          <Route path="/users" element={<UserList />} />
        </Route>

        {/* 兜底：未知路径 → 知识库 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<FullScreenLoading />}>
          <AppRoutes />
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  )
}
