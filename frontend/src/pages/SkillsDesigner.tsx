import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Button, Tag, Space, List, Empty, Input, Select,
  message, Typography, Divider, Form, Switch, Popconfirm, notification, Modal,
} from 'antd'
import {
  PlusOutlined, PlayCircleOutlined, SaveOutlined, DeleteOutlined,
  CopyOutlined, AppstoreOutlined, NodeIndexOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import api from '../api'
import ModuleBanner from '../components/ModuleBanner'

const { Text, Title } = Typography

interface SkillComponent {
  key: string
  name: string
  description: string
  category: string
  params_schema: { name: string; type: string; required: boolean; label: string }[]
  enabled: boolean
}

interface Step {
  skill: string
  params: Record<string, any>
  condition?: string
}

interface Pipeline {
  pipeline_id: string
  name: string
  description: string
  steps: Step[]
  trigger_type: string
  trigger_config: Record<string, any>
  enabled: boolean
}

const CATEGORY_COLORS: Record<string, string> = {
  ai: 'blue', data: 'green', notify: 'orange', security: 'red',
}
const CATEGORY_LABELS: Record<string, string> = {
  ai: '智能能力', data: '数据能力', notify: '通知', security: '安全',
}

const TRIGGER_LABELS: Record<string, string> = {
  cron: '定时触发', event: '事件触发', manual: '手动触发', api: '接口触发',
}

export default function SkillsDesigner() {
  const [components, setComponents] = useState<SkillComponent[]>([])
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [loading, setLoading] = useState(false)
  const [executing, setExecuting] = useState(false)

  // 当前编排草稿
  const [draft, setDraft] = useState<{
    pipeline_id: string; name: string; description: string;
    trigger_type: string; trigger_config?: Record<string, any>; steps: Step[];
  }>({ pipeline_id: '', name: '', description: '', trigger_type: 'manual', trigger_config: {}, steps: [] })

  // 当前草稿是否已保存到已保存列表：true=已保存，可执行；false=脏，需先保存
  const [isSaved, setIsSaved] = useState(false)

  // 选中步骤（用于配置参数）
  const [selectedStep, setSelectedStep] = useState<number | null>(null)
  const [execResult, setExecResult] = useState<any>(null)

  const loadComponents = useCallback(async () => {
    try {
      const data: any = await api.get('/skills/components').then((r: any) => r.data.data)
      setComponents(data.components || [])
    } catch (e: any) {
      message.error('加载组件失败：' + e.message)
    }
  }, [])

  const loadPipelines = useCallback(async () => {
    try {
      const data: any = await api.get('/skills/pipelines').then((r: any) => r.data.data)
      setPipelines(data.pipelines || [])
    } catch (e: any) {
      message.error('加载编排失败：' + e.message)
    }
  }, [])

  useEffect(() => {
    loadComponents()
    loadPipelines()
  }, [loadComponents, loadPipelines])

  const addStep = (comp: SkillComponent) => {
    const params: Record<string, any> = {}
    comp.params_schema.forEach((p) => {
      if (p.type === 'int') params[p.name] = ''
      else params[p.name] = ''
    })
    setDraft((d) => {
      const nextSteps = [...d.steps, { skill: comp.key, params }]
      // 选中新加入的步骤（用新数组长度，避免闭包旧值）
      setSelectedStep(nextSteps.length - 1)
      return { ...d, steps: nextSteps }
    })
    setIsSaved(false)
  }

  const removeStep = (idx: number) => {
    setDraft((d) => {
      const nextSteps = d.steps.filter((_, i) => i !== idx)
      return { ...d, steps: nextSteps }
    })
    // 删除后重置选中，避免右侧面板访问越界 index 导致白屏
    setSelectedStep(null)
    setIsSaved(false)
  }

  // 载入示例模板：一键填几个常用步骤，降低新手使用门槛
  const loadTemplate = () => {
    const keys = ['resume_parse', 'semantic_search', 'talent_match']
    const steps: Step[] = []
    for (const k of keys) {
      const comp = components.find((c) => c.key === k)
      if (!comp) continue
      const params: Record<string, any> = {}
      comp.params_schema.forEach((p) => { params[p.name] = '' })
      steps.push({ skill: comp.key, params })
    }
    if (steps.length === 0) { message.warning('组件尚未加载完成，请稍后再试'); return }
    // 自动生成一个 pipeline_id，避免用户保存时被「请填写编排ID」挡住
    const newPipelineId = `pipe_recruit_${Date.now().toString(36)}`
    setDraft((d) => ({
      ...d,
      pipeline_id: newPipelineId,
      name: '招人智能研判流水线',
      description: '上传简历 → 语义检索人才库 → 匹配在招岗位（示例模板，可修改）',
      steps,
    }))
    setIsSaved(false)
    message.success('已载入示例模板：上传简历→语义检索→岗位匹配，可点左侧组件继续增删')
  }

  const updateStepParam = (idx: number, name: string, value: any) => {
    setDraft((d) => {
      const steps = [...d.steps]
      steps[idx] = { ...steps[idx], params: { ...steps[idx].params, [name]: value } }
      return { ...d, steps }
    })
    setIsSaved(false)
  }

  const savePipeline = async () => {
    if (!draft.pipeline_id || !draft.name || draft.steps.length === 0) {
      message.warning('请填写编排ID、名称并至少添加一个步骤')
      return
    }
    // 若 ID 已存在，二次确认覆盖（避免默默覆盖别人的编排）
    if (pipelines.some((p) => p.pipeline_id === draft.pipeline_id)) {
      Modal.confirm({
        title: '该编排 ID 已存在',
        content: `已存在同名编排「${draft.pipeline_id}」，是否覆盖保存？（原编排将被替换）`,
        okText: '覆盖保存',
        cancelText: '取消',
        onOk: async () => { await doSave() },
      })
      return
    }
    await doSave()
  }
  const doSave = async () => {
    setLoading(true)
    try {
      await api.post('/skills/pipelines', draft)
      message.success('编排已保存')
      setIsSaved(true)  // 标记当前草稿已保存
      await loadPipelines()
    } catch (e: any) {
      const msg = (e.message || '').toString()
      let friendly = '保存失败，请稍后再试'
      if (msg.includes('Network') || msg.includes('Failed to fetch')) {
        friendly = '网络异常，请检查连接后重试'
      } else if (msg) {
        friendly = msg
      }
      message.error(friendly)
    } finally {
      setLoading(false)
    }
  }

  const executePipeline = async () => {
    if (!draft.pipeline_id || !isSaved) {
      notification.warning({
        message: '请先保存编排',
        description: '执行前要先点「保存编排」把当前流程保存下来，才能从已保存列表里调度运行。',
        placement: 'topRight', duration: 4,
      })
      return
    }
    setExecuting(true)
    setExecResult(null)
    try {
      const data: any = await api
        .post(`/skills/pipelines/${draft.pipeline_id}/execute`, { input: {} })
        .then((r: any) => r.data.data)
      setExecResult(data)
      if (data?.success !== false) {
        message.success('编排执行完成')
      } else {
        // 后端返回结构化失败（success=false, outputs=[{step, skill, error}]），
        // 解析后用中文 toast + 友好卡片告诉用户"哪一步错了"，而不是把 JSON 抛给业务用户
        const failedStep = (data?.outputs || []).find((o: any) => o.error) || null
        const friendly = failedStep
          ? `第 ${(failedStep.step ?? 0) + 1} 步「${failedStep.skill || '未知能力'}」执行失败：${(failedStep.error || '').replace(/_/g, ' ')}`
          : '编排执行失败，请检查各步骤的参数是否填写完整'
        notification.error({ message: '执行未完成', description: friendly, placement: 'topRight', duration: 5 })
      }
    } catch (e: any) {
      const msg = (e.message || '').toString()
      let friendly = '执行失败，请稍后再试'
      if (msg.includes('Network') || msg.includes('Failed to fetch')) {
        friendly = '网络异常，请检查连接后重试'
      } else if (msg) {
        friendly = msg
      }
      message.error(friendly)
    } finally {
      setExecuting(false)
    }
  }

  const loadPipeline = (p: Pipeline) => {
    setDraft({
      pipeline_id: p.pipeline_id,
      name: p.name,
      description: p.description,
      trigger_type: p.trigger_type,
      steps: p.steps.map((s) => ({ ...s })),
    })
    setExecResult(null)
    setSelectedStep(null)
    setIsSaved(true)  // 加载已保存的编排，标记为已保存
    message.success(`已加载编排：${p.name}（可点步骤配置参数或执行）`)
  }

  const duplicatePipeline = async (p: Pipeline) => {
    try {
      await api.post(`/skills/pipelines/${p.pipeline_id}/duplicate`, {
        new_pipeline_id: p.pipeline_id + '_copy',
      })
      message.success('已复制')
      await loadPipelines()
    } catch (e: any) {
      message.error('复制失败：' + e.message)
    }
  }

  const deletePipeline = async (p: Pipeline) => {
    try {
      await api.delete(`/skills/pipelines/${p.pipeline_id}`)
      message.success('已删除')
      await loadPipelines()
    } catch (e: any) {
      message.error('删除失败：' + e.message)
    }
  }

  const compMap = (key: string) => components.find((c) => c.key === key)

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>
        自动化流程编排
      </Title>

      <ModuleBanner
        value="把简历解析、人才匹配、数据导出、消息通知等能力封装成可拖拽的流程积木，让「每月人才盘点自动跑」「岗位空缺自动匹配」这类重复劳动交给系统，不再需要每次手工操作或二次开发。"
        relation="当某个人才业务流程固定后，可编排成自动化流程："
        nextLabel="AI 智能体"
        nextPath="/agent"
      />

      <Text type="secondary">
        将业务能力封装为可插拔组件，拖拽组合成自动化流程，支持定时 / 事件 / 手动 / 接口四种触发方式
      </Text>
      <Divider style={{ margin: '12px 0' }} />

      <Row gutter={16}>
        {/* 左：组件库 */}
        <Col span={6}>
          <Card
            title={<Space><AppstoreOutlined />组件库</Space>}
            size="small"
            style={{ height: 560, overflow: 'auto' }}
          >
            <List
              dataSource={components}
              renderItem={(c) => (
                <List.Item
                  key={c.key}
                  style={{ cursor: 'pointer' }}
                  actions={[
                    <Button
                      key="add"
                      type="text"
                      size="small"
                      icon={<PlusOutlined />}
                      onClick={(e) => { e.stopPropagation(); addStep(c) }}
                    />,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space size={4}>
                        <Text strong>{c.name}</Text>
                        <Tag color={CATEGORY_COLORS[c.category] || 'default'}>{CATEGORY_LABELS[c.category] || c.category}</Tag>
                        {!c.enabled && <Tag>停用</Tag>}
                      </Space>
                    }
                    description={c.description}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        {/* 中：编排流程 */}
        <Col span={11}>
          <Card
            title={<Space><NodeIndexOutlined />编排流程</Space>}
            size="small"
            style={{ height: 560, overflow: 'auto' }}
            extra={
              <Space>
                <Input
                  placeholder="编排ID"
                  size="small"
                  style={{ width: 120 }}
                  value={draft.pipeline_id}
                  onChange={(e) => setDraft((d) => ({ ...d, pipeline_id: e.target.value }))}
                />
                <Input
                  placeholder="编排名称"
                  size="small"
                  style={{ width: 140 }}
                  value={draft.name}
                  onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                />
              </Space>
            }
          >
            <Space style={{ marginBottom: 12 }} wrap>
              <Text>触发机制：</Text>
              <Select
                size="small"
                value={draft.trigger_type}
                style={{ width: 120 }}
                onChange={(v) => setDraft((d) => ({ ...d, trigger_type: v }))}
                options={Object.entries(TRIGGER_LABELS).map(([k, v]) => ({ value: k, label: v }))}
              />
              {/* 选了定时触发，提示用户配置 cron 表达式；并附常用模板 */}
              {draft.trigger_type === 'cron' && (
                <Space size={4} wrap>
                  <Text type="secondary" style={{ fontSize: 12 }}>运行时间（cron）：</Text>
                  <Input
                    size="small"
                    placeholder="如 0 9 * * 1（每周一 9:00）"
                    style={{ width: 200 }}
                    value={draft.trigger_config?.cron || ''}
                    onChange={(e) => setDraft((d) => ({
                      ...d,
                      trigger_config: { ...(d.trigger_config || {}), cron: e.target.value },
                    }))}
                  />
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    常用：0 9 * * * 每天 9:00 / 0 */2 * * * 每 2 小时
                  </Typography.Text>
                </Space>
              )}
            </Space>

            {draft.steps.length === 0 ? (
              <Empty description="点击左侧组件添加到流程">
                <Button
                  size="small"
                  type="primary"
                  ghost
                  icon={<ThunderboltOutlined />}
                  onClick={loadTemplate}
                >
                  载入示例模板
                </Button>
              </Empty>
            ) : (
              <div>
                {draft.steps.map((s, idx) => {
                  const comp = compMap(s.skill)
                  return (
                    <div key={idx}>
                      <div
                        onClick={() => setSelectedStep(idx)}
                        style={{
                          border: selectedStep === idx ? '2px solid #4361ee' : '1px solid #e0e0e0',
                          borderRadius: 8, padding: '8px 12px', cursor: 'pointer',
                          background: selectedStep === idx ? '#f0f4ff' : '#fff',
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        }}
                      >
                        <Space>
                          <Text type="secondary" style={{ fontSize: 12 }}>#{idx + 1}</Text>
                          <Text strong>{comp?.name || s.skill}</Text>
                          {s.condition && <Tag color="purple">条件分支</Tag>}
                        </Space>
                        <Space>
                          <Popconfirm title="删除该步骤？" onConfirm={() => removeStep(idx)}>
                            <Button type="text" danger size="small" icon={<DeleteOutlined />} />
                          </Popconfirm>
                        </Space>
                      </div>
                      {idx < draft.steps.length - 1 && (
                        <div style={{ textAlign: 'center', color: '#999', padding: '2px 0' }}>↓</div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            <Divider style={{ margin: '16px 0' }} />
            <Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={loading}
                disabled={draft.steps.length === 0}
                onClick={savePipeline}
              >
                保存编排
              </Button>
              <Button
                icon={<PlayCircleOutlined />}
                loading={executing}
                disabled={draft.steps.length === 0}
                onClick={executePipeline}
              >
                执行
              </Button>
            </Space>
          </Card>
        </Col>

        {/* 右：步骤参数 + 执行结果 */}
        <Col span={7}>
          <Card
            title="步骤参数"
            size="small"
            style={{ height: 270, overflow: 'auto', marginBottom: 16 }}
          >
            {selectedStep === null ? (
              <Empty description="选择步骤配置参数" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              (() => {
                const s = draft.steps[selectedStep]
                if (!s) return <Text type="secondary">步骤不存在</Text>
                const comp = compMap(s.skill)
                if (!comp) return <Text type="secondary">组件不存在</Text>
                return (
                  <Form layout="vertical" size="small">
                    {comp.params_schema.map((p) => (
                      <Form.Item key={p.name} label={p.label} required={p.required}>
                        <Input
                          value={s.params[p.name]}
                          onChange={(e) => updateStepParam(selectedStep, p.name, e.target.value)}
                        />
                      </Form.Item>
                    ))}
                    <Form.Item label="条件分支（可选）">
                      <Input
                        placeholder="如: ctx.data_qa.success"
                        value={s.condition || ''}
                        onChange={(e) => {
                          const steps = [...draft.steps]
                          steps[selectedStep] = { ...steps[selectedStep], condition: e.target.value }
                          setDraft((d) => ({ ...d, steps }))
                        }}
                      />
                    </Form.Item>
                  </Form>
                )
              })()
            )}
          </Card>

          <Card title="执行结果" size="small" style={{ height: 270, overflow: 'auto' }}>
            {execResult ? (
              <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(execResult, null, 2)}
              </pre>
            ) : (
              <Empty description="尚未执行" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      <Divider style={{ margin: '16px 0' }} />
      <Card title="已保存编排（复用/复制/启停）" size="small">
        <List
          dataSource={pipelines}
          locale={{ emptyText: '暂无编排' }}
          renderItem={(p) => (
            <List.Item
              actions={[
                <Button key="load" size="small" onClick={() => loadPipeline(p)}>加载</Button>,
                <Button key="dup" size="small" icon={<CopyOutlined />} onClick={() => duplicatePipeline(p)}>复制</Button>,
                <Switch key="sw" size="small" checked={p.enabled} onChange={async (v) => {
                  await api.post(`/skills/pipelines/${p.pipeline_id}/toggle`, { enabled: v })
                  await loadPipelines()
                }} />,
                <Popconfirm key="del" title="确定删除该编排？" onConfirm={() => deletePipeline(p)} okText="删除" cancelText="取消">
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Text strong>{p.name}</Text>
                    <Tag color="cyan">{TRIGGER_LABELS[p.trigger_type]}</Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>{p.pipeline_id}</Text>
                  </Space>
                }
                description={`${p.steps.length} 个步骤：${p.steps.map((s) => compMap(s.skill)?.name || s.skill).join(' → ')}`}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  )
}
