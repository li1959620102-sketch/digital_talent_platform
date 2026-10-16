import { useEffect, useState } from 'react'
import {
  Card, Button, Upload, message, Space, Typography, Row, Col, Tag,
  Statistic, Empty, Spin, Alert, List, Divider, Modal, Radio, Checkbox, Input,
} from 'antd'
import type { UploadProps } from 'antd'
import {
  UploadOutlined, FileSearchOutlined, ExperimentOutlined, AimOutlined,
  ThunderboltOutlined, CheckCircleFilled, CrownFilled, IdcardOutlined,
  SolutionOutlined,
} from '@ant-design/icons'
import {
  meOverview, uploadMyResume, getMyTalent, getMyRecommendedPaper,
  getMyAssessmentResults, getMyMatchingJobs,
  getPaperQuestions, submitMyAssessment,
} from '../api'
import { useAuth } from '../AuthContext'
import RadarPanel from '../components/RadarPanel'

/** 能力等级 → 展示色/图标 */
const LEVEL_STYLE: Record<string, { color: string; label: string }> = {
  '初级': { color: '#94a3b8', label: '初级' },
  '中级': { color: '#3b82f6', label: '中级' },
  '高级': { color: '#f59e0b', label: '高级' },
  '专家': { color: '#8b5cf6', label: '专家' },
  '骨干': { color: '#22c55e', label: '骨干' },
  '核心人才': { color: '#ef4444', label: '核心人才' },
}

/** 画像能力维度中文名 */
const DIM_CN: Record<string, string> = {
  technical_ability: '专业技术', management_ability: '管理能力',
  communication_ability: '沟通表达', innovation_ability: '创新能力',
  teamwork_ability: '团队协作', learning_ability: '学习能力',
}

export default function MyGrowth() {
  const { user } = useAuth()
  const [, setOverview] = useState<any>(null)
  const [talent, setTalent] = useState<any>(null)
  const [paper, setPaper] = useState<any>(null)
  const [results, setResults] = useState<any[]>([])
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // 真实答题弹框状态（与测评管理一致的体验）
  const [realOpen, setRealOpen] = useState(false)
  const [realLoading, setRealLoading] = useState(false)
  const [realSubmitting, setRealSubmitting] = useState(false)
  const [realQuestions, setRealQuestions] = useState<any[]>([])
  const [realAnswers, setRealAnswers] = useState<Record<number, string>>({})
  const [realResult, setRealResult] = useState<any>(null)
  const [realPaperName, setRealPaperName] = useState<string>('')
  const [uploading, setUploading] = useState(false)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [ov, t, p, res, jb] = await Promise.all([
        meOverview(), getMyTalent(), getMyRecommendedPaper(),
        getMyAssessmentResults(), getMyMatchingJobs(),
      ])
      setOverview(ov)
      setTalent(t)
      setPaper(p?.paper || null)
      setResults(res?.items || [])
      setJobs(jb?.items || [])
    } catch (e: any) {
      message.error(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [])  // eslint-disable-line

  const customUpload: UploadProps['customRequest'] = async (opts: any) => {
    const { file, onSuccess, onError } = opts
    setUploading(true)
    try {
      const res = await uploadMyResume(file)
      onSuccess && onSuccess({}, file)
      message.success(res?.is_new ? '简历已建档，AI 正在生成你的能力画像' : '简历已更新，画像已刷新')
      loadAll()
    } catch (e: any) {
      onError && onError(e)
      message.error(e?.message || '简历解析失败')
    } finally {
      setUploading(false)
    }
  }

  const handleAutoAssess = async () => {
    if (!paper?.id) { message.warning('请先上传简历，系统才能为你推荐测评'); return }
    // 改成真实作答（与测评管理一致），避免直接生成假分数
    setRealPaperName(paper.paper_name || paper.name || '能力测评')
    setRealOpen(true)
    setRealQuestions([])
    setRealAnswers({})
    setRealResult(null)
    setRealLoading(true)
    try {
      const res = await getPaperQuestions(paper.id, false)
      setRealQuestions(res?.items || [])
      if (!res?.items?.length) message.warning('该试卷暂无题目')
    } catch (e: any) {
      message.error(e?.message || '题目加载失败')
      setRealOpen(false)
    } finally {
      setRealLoading(false)
    }
  }

  const handleRealSubmit = async () => {
    if (!paper?.id) return
    const answered = Object.keys(realAnswers).length
    const total = realQuestions.length
    if (answered < total) {
      message.warning(`还有 ${total - answered} 题未作答，确认提交吗？`)
    }
    setRealSubmitting(true)
    try {
      const answers = realQuestions.map((q) => ({
        question_id: q.id,
        answer: realAnswers[q.id] ?? '',
      }))
      const res: any = await submitMyAssessment(paper.id, answers, 0)
      setRealResult(res)
      message.success(`测评完成，正确率 ${res?.accuracy ?? '-'}%`)
      // 刷新最新结果
      const r2 = await getMyAssessmentResults()
      setResults(r2?.items || [])
    } catch (e: any) {
      message.error(e?.message || '提交失败')
    } finally {
      setRealSubmitting(false)
    }
  }

  // 关闭真实答题弹窗的统一入口（取消按钮 / 右上❎ / 提交后点关闭 都走这里）
  const closeRealModal = () => {
    setRealOpen(false)
    setRealResult(null)
    setRealQuestions([])
    setRealAnswers({})
  }

  const portrait = talent?.portrait || {}
  const portraitDims = Object.entries(DIM_CN)
    .map(([k, cn]) => ({ key: k, cn, score: Number(portrait[k]) || 0 }))
    .filter((d) => d.score > 0)

  const hasTalent = !!talent && talent.is_parsed
  const latestResult = results[0]

  // 步骤完成态
  const stepDone: Record<string, boolean> = {
    resume: hasTalent,
    portrait: !!talent && Object.keys(portrait).length > 0,
    assess: results.length > 0,
    match: jobs.length > 0,
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 顶部欢迎条 */}
      <Card
        bordered={false}
        style={{ background: 'linear-gradient(100deg,#eef2ff,#f5f0ff)', borderRadius: 14, border: '1px solid #e0e7ff' }}
      >
        <Row align="middle" justify="space-between">
          <Col>
            <Typography.Title level={4} style={{ margin: 0 }}>
              你好，{user?.username || user?.real_name || '同学'} 👋
            </Typography.Title>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              这里是你的成长工作台：上传简历、认清自己、参与测评、找到更适合的成长方向。
            </Typography.Text>
          </Col>
          <Col>
            {latestResult?.ability_level && (
              <Space direction="vertical" align="end">
                <Tag color={LEVEL_STYLE[latestResult.ability_level]?.color || 'default'} style={{ fontSize: 13, padding: '2px 12px', borderRadius: 20 }}>
                  <CrownFilled /> 当前能力 · {latestResult.ability_level}
                </Tag>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  已完成 {results.length} 次测评
                </Typography.Text>
              </Space>
            )}
          </Col>
        </Row>
      </Card>

      {/* 四步引导 */}
      <Card bordered={false} title={<Space><IdcardOutlined /> 我的成长路径</Space>}>
        <Row gutter={12}>
          {[
            { key: 'resume', icon: <UploadOutlined />, title: '① 上传简历', desc: '系统自动读懂你的经历与技能', color: '#4361ee' },
            { key: 'portrait', icon: <FileSearchOutlined />, title: '② AI 生成画像', desc: '看清自己的优势与待提升点', color: '#8b5cf6' },
            { key: 'assess', icon: <ExperimentOutlined />, title: '③ 能力测评', desc: 'AI 依据画像生成能力报告', color: '#f59e0b' },
            { key: 'match', icon: <AimOutlined />, title: '④ 岗位匹配', desc: '看看自己适合哪些成长方向', color: '#22c55e' },
          ].map((s, i) => (
            <Col xs={12} md={6} key={s.key}>
              <Card size="small" style={{ textAlign: 'center', border: stepDone[s.key] ? '1px solid #22c55e' : '1px solid #f0f0f0', background: stepDone[s.key] ? '#f0fdf4' : '#fff' }}>
                <div style={{ fontSize: 22, color: s.color }}>{s.icon}</div>
                <Typography.Text strong style={{ display: 'block', marginTop: 6 }}>{s.title}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{s.desc}</Typography.Text>
                <div style={{ marginTop: 6 }}>
                  {stepDone[s.key]
                    ? <Tag color="success" icon={<CheckCircleFilled />}>已完成</Tag>
                    : <Tag>待完成</Tag>}
                </div>
                {i < 3 && <span style={{ position: 'absolute', right: -12, top: '50%', color: '#cbd5e1' }}>→</span>}
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 主体：简历上传 + 画像 */}
      <Row gutter={16}>
        {/* 左侧：上传简历 + 我的档案 */}
        <Col xs={24} md={10}>
          <Card bordered={false} title={<Space><UploadOutlined /> 我的简历</Space>}>
            {!hasTalent ? (
              <Upload.Dragger customRequest={customUpload} showUploadList={false} style={{ borderRadius: 12 }}>
                <p className="ant-upload-drag-icon"><UploadOutlined /></p>
                <p className="ant-upload-text">拖拽简历到这里，或点击上传</p>
                <p className="ant-upload-hint">支持 PDF / Word / 图片，系统自动解析并生成你的专属档案（与 HR 人才库隔离）</p>
              </Upload.Dragger>
            ) : (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Alert type="success" showIcon message={`简历已收录：${talent.name}`} description="你可以随时重新上传简历更新档案。" />
                <Button block icon={<UploadOutlined />} loading={uploading} onClick={() => document.getElementById('reupload')?.click()}>
                  重新上传简历
                </Button>
                <input id="reupload" type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg" style={{ display: 'none' }}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) { uploadMyResume(f).then(() => { message.success('简历已更新'); loadAll() }).catch((er: any) => message.error(er.message)); } e.target.value = '' }} />
                <Divider style={{ margin: '8px 0' }} />
                <Typography.Text strong>我的档案信息</Typography.Text>
                {talent && (
                  <Row gutter={[8, 4]} style={{ fontSize: 13 }}>
                    <Col span={12}>职位：{talent.current_position || '—'}</Col>
                    <Col span={12}>年限：{talent.experience_years ?? '—'} 年</Col>
                    <Col span={12}>学历：{talent.education || '—'}</Col>
                    <Col span={12}>专业：{talent.major || '—'}</Col>
                    <Col span={24} style={{ marginTop: 6 }}>
                      <Space size={[4, 4]} wrap>
                        {(talent.skills_certificates || []).map((s: any, i: number) => (
                          <Tag key={i} color="blue">{typeof s === 'string' ? s : s.name}</Tag>
                        ))}
                      </Space>
                    </Col>
                  </Row>
                )}
              </Space>
            )}
          </Card>
        </Col>

        {/* 右侧：AI 画像 */}
        <Col xs={24} md={14}>
          <Card
            bordered={false}
            title={<Space><FileSearchOutlined /> AI 能力画像</Space>}
            extra={hasTalent && portrait?.summary ? <Tag color="green">已生成</Tag> : null}
          >
            {!hasTalent ? (
              <Empty description="上传简历后，AI 将自动生成你的六维能力画像与综合评价" style={{ padding: 30 }} />
            ) : (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                {portraitDims.length > 0 && (
                  <RadarPanel data={Object.fromEntries(portraitDims.map(d => [d.cn, d.score]))} />
                )}
                {portrait?.summary && (
                  <Alert type="info" showIcon={false} message="综合评价" description={portrait.summary} style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }} />
                )}
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      {/* 测评 + 匹配 */}
      <Row gutter={16}>
        <Col xs={24} md={11}>
          <Card bordered={false} title={<Space><ExperimentOutlined /> 我的能力测评</Space>} loading={loading}>
            {!hasTalent ? (
              <Typography.Text type="secondary">先上传简历，系统为你推荐合适的能力测评。</Typography.Text>
            ) : (
              <>
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Typography.Text>为你推荐：<strong>{paper?.paper_name || '—'}</strong></Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {paper?.description || ''}（{results.length ? '已完成测评，可再次挑战提升' : '尚未测评，AI 将依据你的简历智能作答生成能力报告'}）
                  </Typography.Text>
                  <Button type="primary" block icon={<ThunderboltOutlined />} onClick={handleAutoAssess}>
                    {results.length ? '再次 AI 测评 · 检验成长' : '开始 AI 智能测评'}
                  </Button>
                  {results.length > 0 && (
                    <List
                      size="small"
                      dataSource={results}
                      renderItem={(r, idx) => (
                        <List.Item>
                          <Space>
                            <Tag color={LEVEL_STYLE[r.ability_level]?.color || 'default'}>{r.ability_level || '—'}</Tag>
                            <span style={{ fontSize: 13 }}>得分 {r.total_score}</span>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>· {r.submit_time?.slice(0, 16)}</Typography.Text>
                          </Space>
                          {idx === 0 && <Tag color="processing">最近</Tag>}
                        </List.Item>
                      )}
                    />
                  )}
                </Space>
              </>
            )}
          </Card>
        </Col>
        <Col xs={24} md={13}>
          <Card bordered={false} title={<Space><AimOutlined /> 适合我的成长方向</Space>} loading={loading}>
            {!hasTalent ? (
              <Typography.Text type="secondary">上传简历 + 完成测评后，系统会为你推荐合适的岗位方向。</Typography.Text>
            ) : jobs.length === 0 ? (
              <Empty description="完成 AI 测评后，将为你推荐匹配的岗位方向" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={jobs}
                renderItem={(j: any) => (
                  <List.Item>
                    <List.Item.Meta
                      title={<Space><SolutionOutlined style={{ color: '#4361ee' }} />{j.position_name}</Space>}
                      description={`${j.education_requirement || '学历不限'} · ${j.experience_requirement ?? 0}年以上 · ${j.salary_min ? `薪酬 ${j.salary_min/1000}-${j.salary_max/1000}K` : ''}`}
                    />
                    <Space direction="vertical" align="end">
                      <Tag color={j.score >= 80 ? 'success' : j.score >= 60 ? 'orange' : 'default'}>{j.score} 分</Tag>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>{j.match_reason}</Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* 真实作答弹窗（与测评管理一致体验） */}
      <Modal
        title={realResult ? `${realPaperName} · 答题结果` : `真实作答 —— ${realPaperName}`}
        open={realOpen}
        onOk={() => {
          if (realResult) closeRealModal()
          else handleRealSubmit()
        }}
        onCancel={closeRealModal}
        confirmLoading={realSubmitting}
        okText={realResult ? '关闭' : '提交答卷'}
        cancelText={realResult ? '再答一次' : '取消'}
        maskClosable={true}
        keyboard={true}
        width={720}
        destroyOnClose
      >
        {realLoading && <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="题目加载中..." /></div>}
        {!realLoading && realResult && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Row gutter={12}>
              <Col span={6}>
                <Card size="small" style={{ background: '#f6ffed', border: 'none' }}>
                  <Statistic title="正确" value={realResult.correct_count ?? 0} valueStyle={{ fontSize: 20, color: '#22c55e' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#fff1f0', border: 'none' }}>
                  <Statistic title="错误" value={realResult.wrong_count ?? 0} valueStyle={{ fontSize: 20, color: '#ef4444' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#f6f8ff', border: 'none' }}>
                  <Statistic title="得分" value={`${realResult.correct_score ?? 0} / ${realResult.total_score ?? 0}`} valueStyle={{ fontSize: 16, color: '#4361ee' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#fffbe6', border: 'none' }}>
                  <Statistic title="正确率" value={`${realResult.accuracy ?? 0}%`} valueStyle={{ fontSize: 20, color: '#f59e0b' }} />
                </Card>
              </Col>
            </Row>
            <Card size="small" style={{ background: '#f6f8ff' }}>
              <Space><span>综合能力评级：</span><Tag color="purple" style={{ fontSize: 16, padding: '2px 12px' }}>{realResult.ability_level_label || realResult.ability_level || '-'}</Tag></Space>
            </Card>
          </Space>
        )}
        {!realLoading && !realResult && (
          realQuestions.length === 0 ? (
            <Empty description="该试卷暂无题目" />
          ) : (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              {realQuestions.map((q: any, i: number) => {
                const type = q.question_type || 'single'
                const tagMap: Record<string, string> = {
                  single_choice: '单选', multiple_choice: '多选', true_false: '判断',
                  fill_blank: '填空', short_answer: '简答',
                }
                return (
                  <Card key={q.id} size="small" style={{ background: '#fafbff' }}>
                    <Space style={{ marginBottom: 6 }} size={4}>
                      <Tag color="blue">{tagMap[type] || type}</Tag>
                      <b>第 {i + 1} 题</b>（{q.score_value ?? 0} 分）
                    </Space>
                    <div style={{ fontSize: 13, color: '#333', marginBottom: 8 }}>{q.question_content || q.content}</div>
                    {/* 单选 / 判断 */}
                    {(type === 'single_choice' || type === 'true_false') && (
                      <Radio.Group
                        value={realAnswers[q.id]}
                        onChange={(e) => setRealAnswers({ ...realAnswers, [q.id]: e.target.value })}
                      >
                        {(q.options || []).map((opt: any, idx: number) => {
                          const k = typeof opt === 'string' ? String.fromCharCode(65 + idx) : opt.key || opt.label
                          return (
                            <Radio key={k} value={k} style={{ display: 'block', marginBottom: 4 }}>
                              {typeof opt === 'string' ? opt : (opt.label || opt.text)}
                            </Radio>
                          )
                        })}
                        {/* 判断题 fallback：直接 A/B */}
                        {type === 'true_false' && (!q.options || !q.options.length) && (
                          <>
                            <Radio value="正确" style={{ display: 'block' }}>正确</Radio>
                            <Radio value="错误" style={{ display: 'block' }}>错误</Radio>
                          </>
                        )}
                      </Radio.Group>
                    )}
                    {/* 多选 */}
                    {type === 'multiple_choice' && (
                      <Checkbox.Group
                        value={realAnswers[q.id]?.split(',').filter(Boolean) || []}
                        onChange={(vals) => setRealAnswers({ ...realAnswers, [q.id]: vals.join(',') })}
                      >
                        {(q.options || []).map((opt: any, idx: number) => {
                          const k = typeof opt === 'string' ? String.fromCharCode(65 + idx) : opt.key || opt.label
                          return (
                            <Checkbox key={k} value={k} style={{ display: 'block', marginBottom: 4 }}>
                              {typeof opt === 'string' ? opt : (opt.label || opt.text)}
                            </Checkbox>
                          )
                        })}
                      </Checkbox.Group>
                    )}
                    {/* 填空 / 简答 */}
                    {(type === 'fill_blank' || type === 'short_answer') && (
                      <Input.TextArea
                        rows={type === 'fill_blank' ? 1 : 3}
                        placeholder={type === 'fill_blank' ? '请输入答案' : '请输入你的回答'}
                        value={realAnswers[q.id] ?? ''}
                        onChange={(e) => setRealAnswers({ ...realAnswers, [q.id]: e.target.value })}
                      />
                    )}
                  </Card>
                )
              })}
            </Space>
          )
        )}
      </Modal>
    </Space>
  )
}
