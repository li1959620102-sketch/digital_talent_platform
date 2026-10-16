import { useEffect, useState } from 'react'
import {
  Table, Button, Upload, message, Space, Card, Tag, Typography, Tabs,
  Input, Tooltip, notification,
} from 'antd'
import {
  UploadOutlined, ReloadOutlined, FileSearchOutlined, ThunderboltOutlined,
  MessageOutlined, CloudUploadOutlined, DeleteOutlined,
} from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { listKnowledgeFiles, uploadKnowledgeFile, vectorizeKnowledge, askKnowledge, deleteKnowledgeFile, batchDeleteKnowledgeFiles } from '../api'
import { useAuth } from '../AuthContext'
import ModuleBanner from '../components/ModuleBanner'

// 后端 KnowledgeFile.status 合法值：uploaded / vectorized / failed
// 兼容历史脏数据（pending/vectorizing/ready），统一映射展示
const STATUS_TAG: Record<string, { color: string; text: string }> = {
  uploaded: { color: 'default', text: '待处理' },
  vectorizing: { color: 'processing', text: '处理中' },
  vectorized: { color: 'green', text: '已入库' },
  ready: { color: 'green', text: '已入库' },
  pending: { color: 'default', text: '待处理' },
  failed: { color: 'red', text: '失败' },
}
// 知识文件类型 → 中文（兜底完整映射，避免业务用户看到 other 等英文）
const KB_TYPE_CN: Record<string, string> = {
  policy: '规章制度',
  talent_policy: '人才政策',
  product_doc: '产品文档',
  faq: '常见问答',
  training: '培训资料',
  workflow: '流程规范',
  other: '其他',
}

export default function KnowledgeBase() {
  const { hasRole } = useAuth()
  // 管理侧角色才显示"知识文件"上传管理；普通员工专注自助问答
  const isStaff = hasRole('super_admin') || hasRole('admin') || hasRole('hr')
  const [files, setFiles] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [vectorizing, setVectorizing] = useState<number | null>(null)

  // 问答
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<any>(null)
  const [asking, setAsking] = useState(false)

  const load = async (p = page) => {
    setLoading(true)
    try {
      const res = await listKnowledgeFiles({ page: p, page_size: 10 })
      setFiles(res.items || [])
      setTotal(res.total || 0)
      setPage(p)
    } catch (e: any) {
      message.error(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(1) }, [])  // eslint-disable-line

  const customUpload = async (opts: any) => {
    const { file, onSuccess, onError, onProgress } = opts
    // 前端预校验：类型 + 大小（避免无意义请求 + 给用户即时反馈）
    const ALLOWED_EXTS = ['.txt', '.md', '.csv', '.json', '.py', '.pdf', '.docx', '.doc']
    const ext = (file.name || '').toLowerCase().match(/\.[^.]+$/)?.[0] || ''
    if (!ALLOWED_EXTS.includes(ext)) {
      const hint = `不支持的文件类型「${ext || '无扩展名'}」\n仅支持 PDF / Word / 图片 / txt / md / csv / json / py 等文档`
      message.warning(hint, 5)
      onError && onError(new Error(hint))
      return
    }
    const MAX_MB = 50
    if (file.size > MAX_MB * 1024 * 1024) {
      const sizeMb = (file.size / 1024 / 1024).toFixed(1)
      const hint = `文件超过大小限制（单文件最大 ${MAX_MB} MB，当前 ${sizeMb} MB）`
      message.warning(hint, 5)
      onError && onError(new Error(hint))
      return
    }
    setUploading(true)
    try {
      await uploadKnowledgeFile(file, (pct) => onProgress && onProgress({ percent: pct }, file))
      onSuccess && onSuccess({}, file)
      message.success('上传成功')
      load(1)
    } catch (e: any) {
      onError && onError(e)
      // 把后端技术错误翻译成人话
      const msg = (e.message || '').toString()
      let friendly = '上传失败，请稍后再试'
      if (msg.includes('413') || /文件过大|超过/.test(msg)) {
        friendly = '文件超过大小限制（单文件最大 50 MB）'
      } else if (msg.includes('400') || /不支持|格式/.test(msg)) {
        friendly = '文件类型不支持，仅支持 PDF / Word / 图片 / txt / md / csv / json / py'
      } else if (msg.includes('Network') || msg.includes('Failed to fetch')) {
        friendly = '网络异常，请检查连接后重试'
      } else if (msg) {
        friendly = msg
      }
      message.error(friendly, 5)
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteKnowledgeFile(id)
      message.success('删除成功')
      load()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  // 批量删除（整页/跨页选中）
  const [selectedFileKeys, setSelectedFileKeys] = useState<React.ReactText[]>([])
  const [batchDeleting, setBatchDeleting] = useState(false)
  const handleBatchDeleteFiles = async () => {
    if (selectedFileKeys.length === 0) {
      message.warning('请先勾选要删除的文件')
      return
    }
    try {
      setBatchDeleting(true)
      const res = await batchDeleteKnowledgeFiles(selectedFileKeys.map((k) => Number(k)))
      message.success(`批量删除成功：共删除 ${res?.deleted ?? selectedFileKeys.length} 条`)
      setSelectedFileKeys([])
      load()
    } catch (e: any) {
      message.error(e.message || '批量删除失败')
    } finally {
      setBatchDeleting(false)
    }
  }

  const handleVectorize = async (id: number) => {
    setVectorizing(id)
    try {
      await vectorizeKnowledge(id)
      message.success('内容处理完成')
      load()
    } catch (e: any) {
      message.error(e.message || '内容处理失败')
    } finally {
      setVectorizing(null)
    }
  }

  const handleAsk = async (override?: string) => {
    // 优先用调用方传进来的（如点 demo 标签），否则读 state
    const q = (override ?? question).trim()
    if (!q) {
      notification.warning({ message: '请先输入问题', description: '在输入框里写下你想问的问题再点「提问」', placement: 'topRight', duration: 3 })
      return
    }
    setAsking(true)
    setAnswer(null)
    try {
      const res = await askKnowledge(q, 8)
      setAnswer(res)
    } catch (e: any) {
      message.error(e.message || '问答失败')
    } finally {
      setAsking(false)
    }
  }

  const columns = [
    { title: '文件编号', dataIndex: 'file_code', key: 'file_code', width: 160 },
    { title: '文件名', dataIndex: 'file_name', key: 'file_name', ellipsis: true },
    {
      title: '类型', dataIndex: 'knowledge_type', key: 'knowledge_type', width: 90,
      render: (v: string) => KB_TYPE_CN[v] || v || '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => {
        const cfg = STATUS_TAG[v] || { color: 'default', text: v || '-' }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    { title: '切片数', dataIndex: 'chunk_count', key: 'chunk_count', width: 80 },
    {
      title: '可见范围', dataIndex: 'permission_level', key: 'permission_level', width: 90,
      render: (v: number) => {
        // permission_level: 0=全员可见(宽松)，数值越大越受限
        if (v === undefined || v === null) return '-'
        const label = v <= 0 ? '全员可见' : v === 1 ? '登录可见' : v === 2 ? '指定角色' : '高级别'
        return <Tag color={v <= 0 ? 'green' : 'orange'}>{label}</Tag>
      },
    },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: any, r: any) => (
        <Space size="small">
          <Tooltip title="解析内容，用于智能问答检索">
            <Button
              type="link" size="small" icon={<ThunderboltOutlined />}
              loading={vectorizing === r.id}
              onClick={() => handleVectorize(r.id)}
              disabled={r.status === 'ready' || r.status === 'vectorized'}
            >
              {r.status === 'ready' || r.status === 'vectorized' ? '已入库' : '解析入库'}
            </Button>
          </Tooltip>
          <Button
            type="link" size="small" danger icon={<DeleteOutlined />}
            onClick={() => handleDelete(r.id)}
          />
        </Space>
      ),
    },
  ]

  const uploadProps: UploadProps = {
    customRequest: customUpload,
    showUploadList: false,
    accept: '.txt,.md,.csv,.json,.py,.pdf,.docx,.doc',
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><FileSearchOutlined /> 智能知识库</Space>
      </Typography.Title>

      <ModuleBanner
        value={isStaff
          ? '汇聚企业制度、岗位标准、培养方案等资料，提供可溯源、防幻觉的智能问答，并支持分级权限（谁可查什么）。'
          : '把想问的制度、政策、流程直接说出来，AI 基于企业知识库精准回答，答案可溯源到对应文档。'}
        relation={isStaff
          ? '它是员工自助查询、HR 答疑减负的入口：'
          : '企业知识在这里沉淀，你在这里找答案：'}
        nextLabel={isStaff ? '人才档案' : undefined}
        nextPath={isStaff ? '/talents' : undefined}
      />

      <Tabs
        defaultActiveKey={isStaff ? 'files' : 'qa'}
        items={[
          ...(isStaff
            ? [{
                key: 'files',
                label: <span><CloudUploadOutlined /> 知识文件</span>,
                children: (
                  <Card bordered={false}>
                    <Space style={{ marginBottom: 16 }}>
                      <Upload {...uploadProps}>
                        <Button type="primary" icon={<UploadOutlined />} loading={uploading}>上传文档</Button>
                      </Upload>
                      <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
                      <Button danger icon={<DeleteOutlined />} disabled={selectedFileKeys.length === 0} loading={batchDeleting} onClick={handleBatchDeleteFiles}>
                        批量删除{selectedFileKeys.length > 0 ? ` (${selectedFileKeys.length})` : ''}
                      </Button>
                      <Tag color="blue">{total} 个文件</Tag>
                    </Space>
                    <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                      支持 txt/md/csv/json/py/pdf/docx/doc 等格式；上传后点击「解析入库」，系统自动解析内容用于智能问答。
                    </Typography.Text>
                    <Table
                      rowKey="id"
                      loading={loading}
                      dataSource={files}
                      columns={columns}
                      scroll={{ x: 800 }}
                      rowSelection={{
                        selectedRowKeys: selectedFileKeys,
                        onChange: (keys: any) => setSelectedFileKeys(keys),
                        preserveSelectedRowKeys: false,
                      }}
                      pagination={{
                        total,
                        current: page,
                        pageSize: 10,
                        showTotal: (t) => `共 ${t} 条`,
                        onChange: (p) => load(p),
                      }}
                    />
                  </Card>
                ),
              }]
            : []),
          {
            key: 'qa',
            label: <span><MessageOutlined /> 智能问答</span>,
            children: (
              <Card bordered={false}>
                <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                  基于知识库的智能问答：理解问题 → 检索知识 → 生成答案（附来源追溯）。
                </Typography.Text>
                <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
                  <Input
                    placeholder="请输入问题，如：平台有哪些培训课程？"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onPressEnter={() => void handleAsk()}
                    size="large"
                  />
                  <Button type="primary" size="large" icon={<MessageOutlined />} loading={asking} onClick={() => void handleAsk()}>
                    提问
                  </Button>
                </Space.Compact>
                {/* 建议问题：给普通员工/不熟悉业务的用户一点提示，降低"不知道问什么"的门槛 */}
                <div style={{ marginBottom: 16 }}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>试试问：</Typography.Text>
                  <div style={{ marginTop: 6 }}>
                    <Space wrap size={[4, 4]}>
                      {[
                        '平台有哪些培训课程？',
                        '如何上传简历？',
                        '测评结果如何解读？',
                        'AI 能帮我做什么？',
                        '请休假几天？',
                        '岗位匹配是怎么算的？',
                      ].map((s) => (
                        <Tag
                          key={s}
                          color="blue"
                          style={{ cursor: 'pointer' }}
                          onClick={() => { setQuestion(s); setTimeout(() => handleAsk(s), 50) }}
                        >
                          {s}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                </div>
                {asking && <Card loading={asking} style={{ marginBottom: 16 }} />}
                {answer && (
                  <Card title="回答" size="small" style={{ marginBottom: 16 }}>
                    <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                      {answer.answer || answer.response || '（无可读文本，见下方原始结果）'}
                    </Typography.Paragraph>
                    {/* 来源：仅当答案不是"未检索到"兜底文案时才展示，避免误导 */}
                    {Array.isArray(answer.sources) && answer.sources.length > 0 &&
                     !/未检索到|未包含|无法回答|找不到相关|未找到/i.test(answer.answer || '') && (
                      <>
                        <Typography.Text strong>来源：</Typography.Text>
                        {answer.sources.map((s: any, i: number) => (
                          <Tag key={i} color="blue" style={{ margin: 4 }}>
                            {typeof s === 'string' ? s : (s.file_name || s.source || JSON.stringify(s).slice(0, 30))}
                          </Tag>
                        ))}
                      </>
                    )}
                  </Card>
                )}
              </Card>
            ),
          },
        ]}
      />
    </Space>
  )
}
