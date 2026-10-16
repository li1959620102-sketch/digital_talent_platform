import { useState } from 'react'
import { Layout, Menu, Dropdown, Avatar, Typography, Space } from 'antd'
import {
  UserOutlined,
  LogoutOutlined,
  DashboardOutlined,
  TeamOutlined,
  SolutionOutlined,
  FileTextOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BookOutlined,
  AimOutlined,
  FileSearchOutlined,
  RobotOutlined,
  AppstoreOutlined,
  CrownFilled,
  SafetyCertificateFilled,
  TeamOutlined as HRIcon,
  IdcardFilled,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

const { Header, Sider, Content } = Layout

// 菜单项定义（roles 为可见该菜单的角色 code 列表）
interface MenuItem {
  key: string
  label: string
  icon: React.ReactNode
  roles: string[]
}

// 菜单项定义（roles 为可见该菜单的角色 code 列表；group 为分组子标题）
interface MenuItem {
  key: string
  label: string
  icon: React.ReactNode
  roles: string[]
  group?: string
  value?: string
}

// 业务板块分组（子标题）——按「人才全生命周期」业务主线组织，而非功能罗列
const MENU_GROUPS: { key: string; label: string }[] = [
  { key: 'home', label: '工作台' },
  { key: 'talent', label: '人才盘点' },        // 建档案 → 摸清队伍
  { key: 'evaluate', label: '能力评估' },      // 测评 → 看短板
  { key: 'deploy', label: '人岗配置' },        // 匹配 → 用人
  { key: 'grow', label: '培养发展' },          // 培训 → 补短板
  { key: 'ai', label: 'AI 能力' },
  { key: 'system', label: '系统管理' },
]

// 每个菜单项标注它在生命周期里解决的问题（业务价值），作为板块定位
const MENUS: MenuItem[] = [
  // 工作台
  { key: '/',          label: '全局看板', icon: <DashboardOutlined />, roles: ['super_admin', 'admin', 'hr'], group: 'home', value: '总览人才与业务全局' },
  { key: '/me',        label: '我的成长', icon: <IdcardFilled />,       roles: ['user'], group: 'home', value: '上传简历、AI画像、测评与成长方向' },

  // 人才盘点：管人基础
  { key: '/talents',   label: '人才档案', icon: <TeamOutlined />,       roles: ['super_admin', 'admin', 'hr'], group: 'talent', value: '简历入库、人才画像、语义检索' },

  // 能力评估：看清人才
  { key: '/assessments', label: '测评管理', icon: <FileTextOutlined />,  roles: ['super_admin', 'admin', 'hr'], group: 'evaluate', value: '测评题卷、任务下发、结果研判' },

  // 人岗配置：用对人才
  { key: '/positions', label: '岗位管理',   icon: <SolutionOutlined />, roles: ['super_admin', 'admin', 'hr'], group: 'deploy', value: '岗位标准、任职要求' },
  { key: '/matching',  label: '岗位匹配',   icon: <AimOutlined />,       roles: ['super_admin', 'admin', 'hr'], group: 'deploy', value: '人岗双向匹配与推荐' },

  // 培养发展：提升人才
  { key: '/training',  label: '培训管理',   icon: <BookOutlined />,      roles: ['super_admin', 'admin', 'hr'], group: 'grow', value: '课程库、学习计划、效果追踪' },

  // AI 能力（平台差异化）
  { key: '/knowledge', label: '智能知识库', icon: <FileSearchOutlined />, roles: ['super_admin', 'admin', 'hr', 'user'], group: 'ai', value: '制度/政策智能问答，全员可自助' },
  { key: '/agent',     label: 'AI 智能体',  icon: <RobotOutlined />,     roles: ['super_admin', 'admin'], group: 'ai', value: '五大智能体协同' },
  { key: '/skills',    label: '技能编排',   icon: <AppstoreOutlined />,  roles: ['super_admin', 'admin'], group: 'ai', value: 'AI 能力可视化编排' },

  // 系统管理
  { key: '/users',     label: '用户管理',   icon: <SettingOutlined />,   roles: ['super_admin'], group: 'system', value: '账号与角色权限' },
]

// 侧栏 LOGO 区域关键 CSS：让 AntD Sider 内部的 children div 能正确滚动 +
// 滚动条样式与 Sider 深色背景协调（webkit-scrollbar）
const siderCSS = `
.app-sider > div {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.app-sider > div > div:last-child {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  /* 自定义滚动条 - 与深色 Sider 协调 */
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.18) transparent;
  /* 防止 AntD Menu 自动滚到选中项重置 scrollTop */
  overflow-anchor: none;
  scroll-behavior: auto;
}
.app-sider > div > div:last-child::-webkit-scrollbar {
  width: 6px;
}
.app-sider > div > div:last-child::-webkit-scrollbar-track {
  background: transparent;
}
.app-sider > div > div:last-child::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.18);
  border-radius: 3px;
}
.app-sider > div > div:last-child::-webkit-scrollbar-thumb:hover {
  background: rgba(255,255,255,0.32);
}
/* Content 区滚动条与白底协调 */
.app-content-area {
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.18) transparent;
}
.app-content-area::-webkit-scrollbar { width: 8px; }
.app-content-area::-webkit-scrollbar-track { background: transparent; }
.app-content-area::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.18);
  border-radius: 4px;
}
.app-content-area::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.32); }
`

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, hasAnyRole } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  // 按角色过滤可见菜单（RBAC）
  const visibleMenus = MENUS.filter((m) => hasAnyRole(m.roles))

  // 按分组组装菜单（分组子标题 + 菜单项），空分组不展示
  const menuItems = MENU_GROUPS.map((g) => {
    const children = visibleMenus.filter((m) => m.group === g.key)
    if (children.length === 0) return null
    return [
      {
        type: 'group' as const,
        label: g.label,
      },
      ...children.map((m) => ({
        key: m.key,
        label: m.label,
        icon: m.icon,
      })),
    ]
  }).flat().filter(Boolean) as any[]

  const userMenu = {
    items: [
      {
        key: 'logout',
        label: '退出登录',
        icon: <LogoutOutlined />,
      },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === 'logout') {
        logout()
        navigate('/')
      }
    },
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider trigger={null} collapsible collapsed={collapsed} theme="dark" width={220}
        className="app-sider"
        style={{ height: '100vh', position: 'sticky', top: 0 }}
      >
        <div
          style={{
            flexShrink: 0,
            color: '#fff',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            justifyContent: 'center',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            padding: '10px 16px 10px 18px',
            boxSizing: 'border-box',
            overflow: 'hidden',
          }}
        >
          {/* 品牌行：脑图标 LOGO + 平台名 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, height: 40 }}>
            {/* 脑图标 LOGO：环形 orb 装饰 + 深色圆角方形核心 */}
            <div style={{ position: 'relative', width: 38, height: 38, flexShrink: 0 }}>
              {/* 外层环形 orb 装饰（青/粉渐变光晕） */}
              <div style={{
                position: 'absolute',
                inset: -8,
                background: 'conic-gradient(from 0deg, #22d3ee 0deg, #a855f7 90deg, #ec4899 180deg, #22d3ee 270deg, #22d3ee 360deg)',
                borderRadius: '50%',
                filter: 'blur(6px)',
                opacity: 0.55,
              }} />
              {/* 深色圆角方形核心 */}
              <div style={{
                position: 'absolute', inset: 0,
                background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
                borderRadius: 10,
                boxShadow: '0 0 0 1px rgba(34,211,238,0.3), 0 4px 12px rgba(168,85,247,0.4)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {/* 脑图标 SVG */}
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                  <path d="M9.5 2a3.5 3.5 0 0 0-3.4 4.2 3 3 0 0 0-1.6 5.3A3 3 0 0 0 5 16h.5a3 3 0 0 0 3 2.5h.5v2a1 1 0 1 0 2 0V2.1A2.5 2.5 0 0 0 9.5 2z"
                    fill="#22d3ee" opacity="0.9" />
                  <path d="M14.5 2a2.5 2.5 0 0 0-1.5.5V21a1 1 0 1 0 2 0v-2h.5a3 3 0 0 0 3-2.5H19a3 3 0 0 0 .5-4.5 3 3 0 0 0-1.6-5.3A3.5 3.5 0 0 0 14.5 2z"
                    fill="#a855f7" opacity="0.85" />
                  <path d="M9 7.5h2M9 11h2M13 7.5h2M13 11h2M10 14.5h4" stroke="#fff" strokeWidth="1" strokeLinecap="round" opacity="0.85" />
                </svg>
              </div>
              {/* 角点粉色光圈 */}
              <div style={{
                position: 'absolute',
                top: -3, right: -3,
                width: 10, height: 10,
                borderRadius: '50%',
                background: 'radial-gradient(circle, #ec4899 0%, transparent 70%)',
                filter: 'blur(1px)',
              }} />
              <div style={{
                position: 'absolute',
                bottom: -2, left: -2,
                width: 8, height: 8,
                borderRadius: '50%',
                background: 'radial-gradient(circle, #22d3ee 0%, transparent 70%)',
                filter: 'blur(1px)',
              }} />
            </div>
            {!collapsed && (
              <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: 40 }}>
                <span style={{ fontWeight: 700, fontSize: 15, lineHeight: '20px', whiteSpace: 'nowrap', letterSpacing: 0.3, color: '#fff' }}>
                  数智人才平台
                </span>
                <span style={{ fontSize: 10, color: 'rgba(34,211,238,0.7)', marginTop: 2, whiteSpace: 'nowrap', letterSpacing: 1.2 }}>
                  DIGITAL · TALENT
                </span>
              </div>
            )}
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', minHeight: 0 }}>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ minHeight: 0 }}
        />
        </div>
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 1px 4px rgba(0,21,41,0.08)',
          }}
        >
          <Space>
            <span
              style={{ fontSize: 18, cursor: 'pointer', padding: 4 }}
              onClick={() => setCollapsed(!collapsed)}
            >
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </span>
            <Typography.Text strong style={{ fontSize: 16 }}>
              {MENUS.find((m) => m.key === location.pathname)?.label || '数智人才平台'}
            </Typography.Text>
          </Space>
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space style={{ cursor: 'pointer', padding: '4px 8px' }}>
              {/* 按角色渲染身份图标：超级管理员用皇冠（金色发光），管理员用盾牌（紫色），HR 用徽章（蓝色），普通用户用纯灰 */}
              {(() => {
                const roles = user?.roles || []
                const isSuper = roles.includes('super_admin')
                const isAdmin = roles.includes('admin') && !isSuper
                const isHr = roles.includes('hr') && !isSuper && !isAdmin

                let icon: React.ReactNode = <UserOutlined />
                let bg = '#94a3b8'      // 普通用户：中性灰
                let ringColor = 'transparent'
                let ringWidth = 0

                if (isSuper) {
                  icon = <CrownFilled />
                  bg = 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 60%, #d97706 100%)'
                  ringColor = '#fbbf24'
                  ringWidth = 2
                } else if (isAdmin) {
                  icon = <SafetyCertificateFilled />
                  bg = 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)'
                  ringColor = '#a78bfa'
                  ringWidth = 2
                } else if (isHr) {
                  icon = <HRIcon />
                  bg = 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)'
                  ringColor = '#60a5fa'
                  ringWidth = 2
                }

                return (
                  <Avatar
                    icon={icon}
                    style={{
                      background: bg,
                      color: '#fff',
                      boxShadow: ringWidth > 0
                        ? `0 0 0 ${ringWidth}px ${ringColor}40, 0 0 12px ${ringColor}80`
                        : 'none',
                    }}
                  />
                )
              })()}
              <span>{user?.username || user?.real_name}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content
          className="app-content-area"
          style={{
            margin: 24,
            padding: 24,
            background: '#fff',
            borderRadius: 8,
            overflowY: 'auto',
            height: 'calc(100vh - 64px)',
          }}
        >
          {children}
        </Content>
      </Layout>
      <style>{siderCSS}</style>
    </Layout>
  )
}
