import { useState } from 'react'
import {
  Form, Input, Button, message, Typography, Checkbox,
} from 'antd'
import {
  UserOutlined, LockOutlined, MailOutlined, PhoneOutlined,
  RobotOutlined, ThunderboltOutlined, SafetyCertificateOutlined,
  ArrowRightOutlined, GlobalOutlined, TeamOutlined, RiseOutlined,
  ScanOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

// ───────────────────────────────────────────────────────────
//  科技风 AI数字化人才平台 · 登录/注册页
//  设计语言：深色霓虹玻璃态 · 动态光晕 · 分栏（品牌 + 表单）
// ───────────────────────────────────────────────────────────

export default function Login() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [loginForm] = Form.useForm()
  const [registerForm] = Form.useForm()

  // P0 安全加固：与后端 ALLOW_SELF_REGISTER 对齐。
  // 默认关闭游客自助注册（账号由管理员后台创建），隐藏注册入口。
  // 如需开放，后端置 ALLOW_SELF_REGISTER=true，并设 VITE_ALLOW_SELF_REGISTER=true 重新构建。
  const ALLOW_SELF_REGISTER = (import.meta.env.VITE_ALLOW_SELF_REGISTER as string) === 'true'

  const handleLogin = async () => {
    try {
      const values = await loginForm.validateFields()
      setLoading(true)
      const me = await login(values.username, values.password)
      // 按角色决定登录后落点：管理侧进工作台看板，普通员工进"我的成长"
      const roles = me.roles || []
      const isStaff = me.is_superuser || roles.includes('admin') || roles.includes('hr')
      message.success(isStaff ? '登录成功，欢迎回来' : '登录成功')
      setTimeout(() => navigate(isStaff ? '/' : '/me'), 500)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e?.message || '登录失败，请检查账号密码')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async () => {
    try {
      const values = await registerForm.validateFields()
      setLoading(true)
      await register(values)
      // 注册账号默认普通用户，直接进"我的成长"
      message.success('注册成功，已自动登录')
      setTimeout(() => navigate('/me'), 500)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e?.message || '注册失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-root">
      {/* ═══ 背景层：动态渐变光晕 + 网格 + 粒子 ═══ */}
      <div className="bg-layer">
        <div className="bg-aurora aurora-1" />
        <div className="bg-aurora aurora-2" />
        <div className="bg-aurora aurora-3" />
        <div className="bg-grid" />
        <div className="bg-noise" />
      </div>

      {/* ═══ 主体容器（双栏：左品牌/右表单）════ */}
      <div className="auth-shell">
        {/* ── 左：品牌 & 产品卖点（科技插画 + 数据波）── */}
        <div className="brand-panel">
          {/* logo */}
          <div className="brand-logo">
            <div className="logo-ring">
              <div className="logo-core">
                <BrainIcon />
              </div>
              <span className="ring-orb orb-a" />
              <span className="ring-orb orb-b" />
              <span className="ring-orb orb-c" />
            </div>
            <div className="brand-text">
              <div className="brand-title">AI 数字化人才平台</div>
              <div className="brand-sub">Enterprise Talent Intelligence · v1.0</div>
            </div>
          </div>

          {/* 核心标语 */}
          <div className="hero-slogan">
            <div className="slogan-en">RECRUIT · EVALUATE · MATCH · GROW</div>
            <h1 className="slogan-cn">
              让<span className="hl-cyan">AI</span>成为你的
              <br />
              <span className="hl-gradient">首席人才官</span>
            </h1>
            <p className="slogan-desc">
              基于人工智能的企业级人才智能中台，
              覆盖<span className="chip">简历解析</span><span className="chip">素质测评</span>
              <span className="chip">岗位匹配</span><span className="chip">培训赋能</span>
              <span className="chip">数据决策</span>全生命周期。
            </p>
          </div>

          {/* 4 个核心能力胶囊 */}
          <div className="pill-grid">
            <FeaturePill
              icon={<ScanOutlined />}
              title="智能解析"
              desc="多格式简历秒级结构化"
              accent="cyan"
            />
            <FeaturePill
              icon={<ThunderboltOutlined />}
              title="AI 匹配"
              desc="岗位/人才语义级精准推荐"
              accent="magenta"
            />
            <FeaturePill
              icon={<SafetyCertificateOutlined />}
              title="测评分析"
              desc="多维度能力雷达与成长画像"
              accent="violet"
            />
            <FeaturePill
              icon={<RiseOutlined />}
              title="决策驾驶舱"
              desc="人才数据实时可视化洞察"
              accent="amber"
            />
          </div>

          {/* 数据波（SVG 装饰） */}
          <div className="wave-wrap">
            <DataWaveSVG />
          </div>

          {/* 底部统计条 */}
          <div className="footer-stats">
            <StatItem icon={<TeamOutlined />} num="40+" label="人才档案" />
            <div className="stat-divider" />
            <StatItem icon={<GlobalOutlined />} num="6" label="AI 智能体" />
            <div className="stat-divider" />
            <StatItem icon={<RobotOutlined />} num="5" label="核心模块" />
            <div className="stat-divider" />
            <StatItem icon={<SafetyCertificateOutlined />} num="4" label="权限角色" />
          </div>
        </div>

        {/* ── 右：玻璃态表单卡片 ── */}
        <div className="form-panel">
          <div className="form-glass">
            {/* 顶部装饰条 */}
            <div className="form-top-accent" />

            {/* Tab 导航 */}
            <div className="tabs-wrap">
              <button
                className={`tab-btn ${tab === 'login' ? 'active' : ''}`}
                onClick={() => setTab('login')}
              >
                <span className="tab-dot" />
                登录账号
              </button>
              {ALLOW_SELF_REGISTER && (
                <button
                  className={`tab-btn ${tab === 'register' ? 'active' : ''}`}
                  onClick={() => setTab('register')}
                >
                  <span className="tab-dot" />
                  注册新用户
                </button>
              )}
            </div>

            {/* 内容区 */}
            <div className="form-body">
              <div className="form-head">
                <div className="form-kicker">
                  {tab === 'login' ? 'WELCOME BACK' : 'JOIN THE FUTURE'}
                </div>
                <h2 className="form-title">
                  {tab === 'login' ? '登录你的工作台' : '创建你的账户'}
                </h2>
                <p className="form-sub">
                  {tab === 'login'
                    ? '使用已注册账号进入 AI 数字化人才平台'
                    : '公开注册默认为「普通用户」角色，HR/管理员可由超管授权'}
                </p>
              </div>

              {tab === 'login' ? (
                <Form
                  form={loginForm}
                  onFinish={handleLogin}
                  layout="vertical"
                  size="large"
                  requiredMark={false}
                >
                  <Form.Item
                    label={<span className="field-label">账号 / 用户名</span>}
                    name="username"
                    rules={[{ required: true, message: '请输入用户名' }]}
                  >
                    <Input
                      prefix={<UserOutlined className="field-icon" />}
                      placeholder="请输入用户名，例如 admin"
                      autoComplete="username"
                      className="tech-input"
                    />
                  </Form.Item>
                  <Form.Item
                    label={<span className="field-label">登录密码</span>}
                    name="password"
                    rules={[{ required: true, message: '请输入密码' }]}
                  >
                    <Input.Password
                      prefix={<LockOutlined className="field-icon" />}
                      placeholder="请输入密码"
                      autoComplete="current-password"
                      className="tech-input"
                    />
                  </Form.Item>

                  <div className="row-between">
                    <Form.Item name="remember" valuePropName="checked" noStyle>
                      <Checkbox className="tech-check">7 天内免登录</Checkbox>
                    </Form.Item>
                    <a className="link-muted" onClick={() => message.info('请联系管理员重置密码')}>
                      忘记密码？
                    </a>
                  </div>

                  <Button
                    type="primary"
                    htmlType="submit"
                    block
                    loading={loading}
                    size="large"
                    className="submit-btn"
                    icon={<ArrowRightOutlined />}
                    iconPosition="end"
                  >
                    进入平台
                  </Button>
                </Form>
              ) : (
                <Form
                  form={registerForm}
                  onFinish={handleRegister}
                  layout="vertical"
                  size="large"
                  requiredMark={false}
                >
                  <Form.Item
                    label={<span className="field-label">用户名</span>}
                    name="username"
                    rules={[
                      { required: true, message: '请设置用户名' },
                      { min: 3, message: '用户名至少 3 个字符' },
                    ]}
                  >
                    <Input
                      prefix={<UserOutlined className="field-icon" />}
                      placeholder="3-20 位字母、数字或下划线"
                      autoComplete="username"
                      className="tech-input"
                    />
                  </Form.Item>
                  <Form.Item
                    label={<span className="field-label">登录密码</span>}
                    name="password"
                    rules={[
                      { required: true, message: '请设置密码' },
                      { min: 12, message: '密码至少 12 位' },
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined className="field-icon" />}
                      placeholder="至少 12 位，建议包含字母、数字、符号"
                      autoComplete="new-password"
                      className="tech-input"
                    />
                  </Form.Item>

                  <div className="two-col">
                    <Form.Item label={<span className="field-label">真实姓名</span>} name="real_name">
                      <Input
                        prefix={<UserOutlined className="field-icon" />}
                        placeholder="选填"
                        className="tech-input"
                      />
                    </Form.Item>
                    <Form.Item
                      label={<span className="field-label">邮箱</span>}
                      name="email"
                      rules={[{ type: 'email', message: '邮箱格式不正确' }]}
                    >
                      <Input
                        prefix={<MailOutlined className="field-icon" />}
                        placeholder="选填，用于接收通知"
                        autoComplete="email"
                        className="tech-input"
                      />
                    </Form.Item>
                  </div>

                  <Form.Item label={<span className="field-label">手机号</span>} name="phone">
                    <Input
                      prefix={<PhoneOutlined className="field-icon" />}
                      placeholder="选填，11 位手机号"
                      autoComplete="tel"
                      className="tech-input"
                    />
                  </Form.Item>

                  <Form.Item
                    name="agreement"
                    valuePropName="checked"
                    rules={[{
                      validator: (_, v) => v
                        ? Promise.resolve()
                        : Promise.reject(new Error('请先阅读并同意用户协议')),
                    }]}
                  >
                    <Checkbox className="tech-check">
                      我已阅读并同意<a className="link-muted" onClick={(e) => e.preventDefault()}>《用户协议》</a>和
                      <a className="link-muted" onClick={(e) => e.preventDefault()}>《隐私政策》</a>
                    </Checkbox>
                  </Form.Item>

                  <Button
                    type="primary"
                    htmlType="submit"
                    block
                    loading={loading}
                    size="large"
                    className="submit-btn"
                    icon={<ArrowRightOutlined />}
                    iconPosition="end"
                  >
                    立即注册并登录
                  </Button>
                </Form>
              )}

              <Typography.Paragraph className="foot-tip">
                © 2026 AI 数字化人才平台 · 提供人才全生命周期智能化服务
              </Typography.Paragraph>
            </div>
          </div>
        </div>
      </div>

      {/* ═══ 样式（内联注入，避免污染其他页面）════ */}
      <style>{styles}</style>
    </div>
  )
}

// ─────────────── 小组件 ───────────────

function FeaturePill({
  icon, title, desc, accent,
}: { icon: React.ReactNode; title: string; desc: string; accent: 'cyan' | 'magenta' | 'violet' | 'amber' }) {
  return (
    <div className={`feature-pill accent-${accent}`}>
      <div className="fp-icon">{icon}</div>
      <div className="fp-text">
        <div className="fp-title">{title}</div>
        <div className="fp-desc">{desc}</div>
      </div>
    </div>
  )
}

function StatItem({ icon, num, label }: { icon: React.ReactNode; num: string; label: string }) {
  return (
    <div className="stat-item">
      <div className="stat-icon">{icon}</div>
      <div className="stat-text">
        <div className="stat-num">{num}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}

function BrainIcon() {
  return (
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M9 3a3 3 0 0 0-3 3v1a3 3 0 0 0-2 5.2A3 3 0 0 0 5 17a3 3 0 0 0 3 3 3 3 0 0 0 1 .2V21h6v-.8a3 3 0 0 0 1-.2 3 3 0 0 0 3-3 3 3 0 0 0-1-4.8A3 3 0 0 0 18 7V6a3 3 0 0 0-3-3 3 3 0 0 0-2 .8A3 3 0 0 0 11 3a3 3 0 0 0-2 .8A3 3 0 0 0 9 3Z"
        stroke="url(#brain-g)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 4v16M9 7h1M14 7h1M9 12h1M14 12h1M9 17h1M14 17h1"
        stroke="url(#brain-g)" strokeWidth="1.4" strokeLinecap="round" />
      <defs>
        <linearGradient id="brain-g" x1="0" y1="0" x2="24" y2="24">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="50%" stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#f472b6" />
        </linearGradient>
      </defs>
    </svg>
  )
}

function DataWaveSVG() {
  return (
    <svg viewBox="0 0 520 90" preserveAspectRatio="none" className="wave-svg">
      <defs>
        <linearGradient id="waveA" x1="0" x2="1">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0" />
          <stop offset="50%" stopColor="#22d3ee" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="waveB" x1="0" x2="1">
          <stop offset="0%" stopColor="#f472b6" stopOpacity="0" />
          <stop offset="50%" stopColor="#f472b6" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="waveC" x1="0" x2="1">
          <stop offset="0%" stopColor="#a78bfa" stopOpacity="0" />
          <stop offset="50%" stopColor="#a78bfa" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#f472b6" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[
        { id: 'waveA', d: 'M0 45 Q 60 10 120 45 T 240 45 T 360 45 T 520 45', w: 1.8 },
        { id: 'waveB', d: 'M0 60 Q 70 20 140 60 T 280 60 T 420 60 T 520 60', w: 1.2 },
        { id: 'waveC', d: 'M0 30 Q 50 55 100 30 T 200 30 T 300 30 T 400 30 T 520 30', w: 0.9 },
      ].map((w, i) => (
        <path
          key={i}
          d={w.d}
          fill="none"
          stroke={`url(#${w.id})`}
          strokeWidth={w.w * 2}
          strokeLinecap="round"
        >
          <animate
            attributeName="stroke-dasharray"
            values="0 1200;480 1200;0 1200"
            dur={`${7 + i * 2}s`}
            repeatCount="indefinite"
          />
          <animate
            attributeName="stroke-dashoffset"
            values="0;-480;-960"
            dur={`${7 + i * 2}s`}
            repeatCount="indefinite"
          />
        </path>
      ))}
      {/* 数据点 */}
      {[15, 60, 110, 165, 220, 275, 330, 390, 445, 500].map((cx, i) => (
        <circle key={i} cx={cx} cy={40 + Math.sin(i) * 15} r="2.2" fill="#22d3ee">
          <animate
            attributeName="r"
            values="1.2;3.2;1.2"
            dur={`${2.2 + (i % 5) * 0.3}s`}
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.3;1;0.3"
            dur={`${2.2 + (i % 5) * 0.3}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
    </svg>
  )
}

// ─────────────── 样式 ───────────────
const styles = `
/* ----------- 根容器 ----------- */
.auth-root {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  color: #e5e7eb;
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  background:
    radial-gradient(1200px 600px at 8% -10%, rgba(34,211,238,0.18), transparent 60%),
    radial-gradient(900px 500px at 100% 10%, rgba(244,114,182,0.15), transparent 60%),
    radial-gradient(1000px 700px at 50% 120%, rgba(167,139,250,0.20), transparent 60%),
    linear-gradient(180deg, #05070d 0%, #0a0f1e 50%, #060a14 100%);
}

/* ----------- 背景装饰 ----------- */
.bg-layer { position: absolute; inset: 0; pointer-events: none; }
.bg-aurora {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.55;
  mix-blend-mode: screen;
  animation: float 16s ease-in-out infinite;
}
.aurora-1 { width: 520px; height: 520px; top: -120px; left: -80px;
  background: radial-gradient(circle, #22d3ee 0%, transparent 60%); }
.aurora-2 { width: 560px; height: 560px; top: 40%; right: -160px;
  background: radial-gradient(circle, #f472b6 0%, transparent 60%);
  animation-delay: -4s; }
.aurora-3 { width: 480px; height: 480px; bottom: -140px; left: 30%;
  background: radial-gradient(circle, #a78bfa 0%, transparent 60%);
  animation-delay: -8s; }
@keyframes float {
  0%,100% { transform: translate3d(0,0,0) scale(1); }
  50%     { transform: translate3d(0,-30px,0) scale(1.06); }
}
.bg-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(148,163,184,0.07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148,163,184,0.07) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse at center, #000 40%, transparent 80%);
}
.bg-noise {
  position: absolute; inset: 0;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.06 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
  opacity: 0.4;
}

/* ----------- 主体 ----------- */
.auth-shell {
  position: relative;
  z-index: 2;
  max-width: 1280px;
  margin: 0 auto;
  min-height: 100vh;
  padding: 36px 40px;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 40px;
  align-items: stretch;
}

/* ===== 左：品牌 ===== */
.brand-panel {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 28px 8px;
  gap: 28px;
}
.brand-logo { display: flex; align-items: center; gap: 18px; }
.logo-ring {
  position: relative;
  width: 64px; height: 64px;
  display: grid; place-items: center;
  border-radius: 20px;
  background: conic-gradient(from 140deg, #22d3ee, #a78bfa, #f472b6, #22d3ee);
  box-shadow: 0 0 0 1px rgba(255,255,255,0.08), 0 12px 40px rgba(34,211,238,0.25);
  animation: ringspin 9s linear infinite;
}
@keyframes ringspin { to { transform: rotate(360deg); } }
.logo-core {
  width: 52px; height: 52px; border-radius: 16px;
  background: linear-gradient(135deg, #0b1224, #111a35);
  display: grid; place-items: center;
  animation: ringspin 9s linear infinite reverse;
}
.ring-orb {
  position: absolute; width: 10px; height: 10px; border-radius: 50%;
  box-shadow: 0 0 12px currentColor;
}
.orb-a { top: -4px; left: 28px; color: #22d3ee; background: #22d3ee; }
.orb-b { bottom: 2px; left: -2px; color: #f472b6; background: #f472b6; }
.orb-c { bottom: 2px; right: -2px; color: #a78bfa; background: #a78bfa; }

.brand-text { display: flex; flex-direction: column; line-height: 1.2; }
.brand-title {
  font-size: 22px; font-weight: 700; letter-spacing: 0.5px;
  background: linear-gradient(90deg, #e0f2fe, #c4b5fd 55%, #fbcfe8);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.brand-sub { font-size: 12px; letter-spacing: 2px; color: #64748b; margin-top: 4px; }

/* hero slogan */
.hero-slogan { margin-top: 8px; }
.slogan-en {
  display: inline-block;
  padding: 6px 14px; border-radius: 999px;
  background: linear-gradient(90deg, rgba(34,211,238,0.15), rgba(167,139,250,0.15));
  border: 1px solid rgba(148,163,184,0.22);
  color: #94a3b8;
  font-size: 12px; letter-spacing: 3px; font-weight: 600;
  backdrop-filter: blur(6px);
}
.slogan-cn {
  margin: 18px 0 14px;
  font-size: 44px; line-height: 1.18; font-weight: 800;
  color: #f8fafc;
  letter-spacing: 0.5px;
}
.hl-cyan {
  color: #22d3ee;
  text-shadow: 0 0 18px rgba(34,211,238,0.5);
  padding: 0 2px;
}
.hl-gradient {
  background: linear-gradient(90deg, #22d3ee 0%, #a78bfa 50%, #f472b6 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 4px 18px rgba(167,139,250,0.35));
}
.slogan-desc {
  font-size: 15px; line-height: 1.8; color: #94a3b8;
  max-width: 540px; margin: 0;
}
.chip {
  display: inline-block; margin: 2px 4px 0 0;
  padding: 2px 10px; border-radius: 6px;
  font-size: 12px; font-weight: 600;
  background: rgba(148,163,184,0.08);
  border: 1px solid rgba(148,163,184,0.18);
  color: #cbd5e1;
}

/* 特性胶囊 */
.pill-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
  margin-top: 4px;
}
.feature-pill {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
  border: 1px solid rgba(148,163,184,0.14);
  backdrop-filter: blur(10px);
  transition: transform .25s ease, border-color .25s ease, box-shadow .25s ease;
}
.feature-pill:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 38px rgba(0,0,0,0.35);
}
.accent-cyan     { border-color: rgba(34,211,238,0.35); }
.accent-magenta  { border-color: rgba(244,114,182,0.35); }
.accent-violet   { border-color: rgba(167,139,250,0.35); }
.accent-amber    { border-color: rgba(251,191,36,0.35); }
.fp-icon {
  width: 42px; height: 42px; border-radius: 12px;
  display: grid; place-items: center;
  font-size: 18px;
  background: linear-gradient(135deg, rgba(34,211,238,0.18), rgba(167,139,250,0.18));
  color: #a78bfa;
}
.accent-cyan    .fp-icon { color: #22d3ee; background: linear-gradient(135deg, rgba(34,211,238,0.22), rgba(34,211,238,0.05)); }
.accent-magenta .fp-icon { color: #f472b6; background: linear-gradient(135deg, rgba(244,114,182,0.22), rgba(244,114,182,0.05)); }
.accent-violet  .fp-icon { color: #a78bfa; background: linear-gradient(135deg, rgba(167,139,250,0.22), rgba(167,139,250,0.05)); }
.accent-amber   .fp-icon { color: #fbbf24; background: linear-gradient(135deg, rgba(251,191,36,0.22), rgba(251,191,36,0.05)); }
.fp-title { font-size: 15px; font-weight: 700; color: #e2e8f0; }
.fp-desc  { font-size: 12px; color: #64748b; margin-top: 2px; }

/* 数据波 */
.wave-wrap {
  margin-top: 10px;
  border-radius: 18px;
  padding: 10px 6px;
  background:
    linear-gradient(180deg, rgba(15,23,42,0.5), rgba(2,6,23,0.7)),
    radial-gradient(800px 200px at 50% 0%, rgba(34,211,238,0.08), transparent 70%);
  border: 1px solid rgba(148,163,184,0.15);
  backdrop-filter: blur(6px);
}
.wave-svg { width: 100%; height: 90px; display: block; }

/* 底部统计 */
.footer-stats {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px;
  border-radius: 16px;
  background: rgba(15,23,42,0.4);
  border: 1px solid rgba(148,163,184,0.12);
  backdrop-filter: blur(8px);
}
.stat-item { display: flex; align-items: center; gap: 12px; flex: 1; }
.stat-icon {
  width: 38px; height: 38px; border-radius: 10px;
  display: grid; place-items: center;
  color: #22d3ee;
  background: rgba(34,211,238,0.1);
  border: 1px solid rgba(34,211,238,0.2);
  font-size: 16px;
}
.stat-num { font-size: 18px; font-weight: 800; color: #f1f5f9; line-height: 1.1; }
.stat-label { font-size: 12px; color: #64748b; margin-top: 2px; }
.stat-divider {
  width: 1px; align-self: stretch; margin: 6px 10px;
  background: linear-gradient(180deg, transparent, rgba(148,163,184,0.3), transparent);
}

/* ===== 右：表单 ===== */
.form-panel {
  display: flex; align-items: center; justify-content: center;
  padding: 10px 0;
}
.form-glass {
  position: relative;
  width: 100%;
  max-width: 480px;
  border-radius: 24px;
  padding: 0 0 28px;
  background:
    linear-gradient(160deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.02) 60%, rgba(255,255,255,0.04) 100%);
  border: 1px solid rgba(255,255,255,0.10);
  backdrop-filter: blur(18px) saturate(160%);
  -webkit-backdrop-filter: blur(18px) saturate(160%);
  box-shadow:
    0 30px 80px rgba(2,6,23,0.55),
    inset 0 1px 0 rgba(255,255,255,0.08);
  overflow: hidden;
}
.form-top-accent {
  position: absolute; inset: 0 0 auto 0; height: 4px;
  background: linear-gradient(90deg,
    transparent 0%,
    #22d3ee 25%,
    #a78bfa 50%,
    #f472b6 75%,
    transparent 100%);
  filter: blur(0.2px);
  animation: sheen 4.5s linear infinite;
}
@keyframes sheen {
  0%   { transform: translateX(-100%); opacity: 0.2; }
  40%  { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0.2; }
}

.tabs-wrap {
  display: grid; grid-template-columns: 1fr 1fr;
  padding: 22px 22px 0;
}
.tab-btn {
  position: relative;
  padding: 14px 0;
  background: transparent;
  border: none; outline: none; cursor: pointer;
  color: #64748b;
  font-size: 15px; font-weight: 600;
  letter-spacing: 0.5px;
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border-bottom: 2px solid rgba(148,163,184,0.15);
  transition: color .2s ease, border-color .2s ease;
}
.tab-btn:hover { color: #cbd5e1; }
.tab-btn.active {
  color: #f8fafc;
  border-bottom-color: transparent;
}
.tab-btn.active::after {
  content: "";
  position: absolute; left: 10%; right: 10%; bottom: -2px; height: 2px;
  border-radius: 2px;
  background: linear-gradient(90deg, #22d3ee, #a78bfa, #f472b6);
  box-shadow: 0 0 18px rgba(167,139,250,0.6);
}
.tab-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #334155;
  transition: all .2s ease;
}
.tab-btn.active .tab-dot {
  background: #22d3ee;
  box-shadow: 0 0 10px rgba(34,211,238,0.75);
}

.form-body { padding: 22px 32px 6px; }
.form-head { margin-bottom: 18px; }
.form-kicker {
  font-size: 11px; letter-spacing: 3px; font-weight: 700;
  color: #22d3ee;
}
.form-title {
  margin: 6px 0 4px;
  font-size: 24px; font-weight: 800; color: #f8fafc;
  letter-spacing: 0.3px;
}
.form-sub { margin: 0; font-size: 13px; color: #64748b; line-height: 1.6; }

.field-label { font-size: 13px; font-weight: 600; color: #cbd5e1; letter-spacing: 0.3px; }
.field-icon { color: #64748b; }

/* 科技风输入框 */
.tech-input {
  background: rgba(15,23,42,0.55) !important;
  border-color: rgba(148,163,184,0.22) !important;
  color: #e2e8f0 !important;
  border-radius: 12px !important;
  transition: all .2s ease !important;
  box-shadow: none !important;
}
.tech-input:hover { border-color: rgba(34,211,238,0.4) !important; }
.tech-input:focus-within,
.tech-input.ant-input-affix-wrapper-focused {
  border-color: #22d3ee !important;
  background: rgba(15,23,42,0.75) !important;
  box-shadow: 0 0 0 3px rgba(34,211,238,0.15) !important;
}
.tech-input input { background: transparent !important; color: #e2e8f0 !important; }
.tech-input input::placeholder { color: #475569 !important; }
.ant-input-outlined.tech-input { padding: 10px 12px !important; }

.row-between {
  display: flex; justify-content: space-between; align-items: center;
  margin: -4px 0 16px;
}
.tech-check .ant-checkbox-inner {
  background: rgba(15,23,42,0.55) !important;
  border-color: rgba(148,163,184,0.3) !important;
  border-radius: 4px;
}
.tech-check { color: #94a3b8; font-size: 13px; }
.tech-check.ant-checkbox-wrapper:hover .ant-checkbox-inner,
.tech-check .ant-checkbox-checked .ant-checkbox-inner {
  border-color: #22d3ee !important;
  background-color: #22d3ee !important;
}
.link-muted {
  color: #22d3ee;
  font-size: 13px; cursor: pointer;
  text-decoration: none;
  transition: filter .15s ease;
}
.link-muted:hover { color: #67e8f9; text-decoration: underline; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* 提交按钮 */
.submit-btn {
  height: 48px !important;
  margin-top: 6px !important;
  border: none !important;
  border-radius: 12px !important;
  font-weight: 700 !important;
  letter-spacing: 0.6px;
  color: #020617 !important;
  background: linear-gradient(90deg, #22d3ee 0%, #a78bfa 55%, #f472b6 100%) !important;
  background-size: 200% 100% !important;
  box-shadow:
    0 10px 30px rgba(34,211,238,0.20),
    0 0 0 1px rgba(255,255,255,0.08) inset !important;
  transition: all .3s ease !important;
}
.submit-btn:hover:not(:disabled) {
  background-position: 100% 0 !important;
  box-shadow:
    0 18px 44px rgba(167,139,250,0.32),
    0 0 0 1px rgba(255,255,255,0.12) inset !important;
  transform: translateY(-1px);
}
.submit-btn:active { transform: translateY(0) scale(0.995); }

.divider-dashed {
  border-color: rgba(148,163,184,0.18) !important;
  margin: 22px 0 16px !important;
}
.divider-text { color: #64748b; font-size: 12px; letter-spacing: 1.5px; }

.demo-alert {
  --antd-alert-bg: rgba(15,23,42,0.45) !important;
  --antd-alert-border-color: rgba(34,211,238,0.25) !important;
  border-radius: 12px;
  border: 1px solid rgba(34,211,238,0.25) !important;
  background: rgba(15,23,42,0.45) !important;
}
.demo-alert .ant-alert-message { color: #cbd5e1; font-size: 13px; }
.demo-code {
  padding: 2px 8px; border-radius: 6px;
  background: rgba(15,23,42,0.7);
  border: 1px solid rgba(148,163,184,0.2);
  color: #22d3ee;
  font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
  font-size: 12px;
}

.foot-tip {
  text-align: center;
  color: #475569;
  font-size: 11.5px;
  letter-spacing: 0.3px;
  margin: 20px 0 0 !important;
}

/* ========== 响应式 ========== */
@media (max-width: 1080px) {
  .auth-shell {
    grid-template-columns: 1fr;
    padding: 24px 18px;
    gap: 20px;
  }
  .brand-panel { display: none; }
  .form-glass { max-width: 100%; }
}
@media (max-width: 520px) {
  .two-col { grid-template-columns: 1fr; gap: 0; }
  .form-body { padding: 18px 20px 2px; }
  .slogan-cn { font-size: 32px; }
  .pill-grid { grid-template-columns: 1fr; }
}
`
