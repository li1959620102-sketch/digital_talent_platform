import { useEffect, useState } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, message, Space, Card,
  Tag, Row, Col, Typography, Badge, Popconfirm, Descriptions,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, SolutionOutlined, DeleteOutlined,
  EditOutlined, EyeOutlined,
} from '@ant-design/icons'
import {
  listPositions, createPosition, batchDeletePositions, deletePosition, updatePosition,
  listOrganizations,
} from '../api'
import ModuleBanner from '../components/ModuleBanner'

const LEVEL_OPTIONS = [
  { value: 'entry', label: '初级' },
  { value: 'junior', label: '初级+' },
  { value: 'intermediate', label: '中级' },
  { value: 'senior', label: '高级' },
  { value: 'expert', label: '专家' },
  { value: 'manager', label: '经理' },
  { value: 'director', label: '总监' },
]
const STATUS_TAG: Record<string, { color: string; text: string }> = {
  open: { color: 'green', text: '招聘中' },
  closed: { color: 'default', text: '已关闭' },
  suspended: { color: 'orange', text: '已暂停' },
  draft: { color: 'blue', text: '草稿' },
}

const LEVEL_LABEL: Record<string, string> = LEVEL_OPTIONS.reduce((acc, o) => {
  acc[o.value] = o.label
  return acc
}, {} as Record<string, string>)

export default function PositionList() {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState({ keyword: '', position_level: '', status: '' })
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  // 组织/部门列表（下拉用）
  const [orgs, setOrgs] = useState<any[]>([])
  // 编辑弹窗
  const [editing, setEditing] = useState<any>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editForm] = Form.useForm()
  // 详情弹窗
  const [detail, setDetail] = useState<any>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const loadOrgs = async () => {
    try {
      const list = await listOrganizations()
      setOrgs(list || [])
    } catch (e: any) {
      // 组织列表加载失败不阻断主流程
      console.error('组织列表加载失败', e)
    }
  }

  useEffect(() => { loadOrgs() }, [])  // eslint-disable-line

  const load = async (p = page, ps = pageSize, filters = search) => {
    setLoading(true)
    try {
      const res = await listPositions({ page: p, page_size: ps, ...filters })
      setData(res.items || [])
      setTotal(res.total || 0)
    } catch (e: any) {
      message.error(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(1, 10, search) }, [])  // eslint-disable-line

  const onSearch = () => {
    setPage(1)
    load(1, pageSize, search)
  }

  const onReset = () => {
    const empty = { keyword: '', position_level: '', status: '' }
    setSearch(empty)
    setPage(1)
    load(1, pageSize, empty)
  }

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      // skill_requirements: 字符串转数组
      const skillReq = (values.skill_requirements || '').split(',').map((s: string) => s.trim()).filter(Boolean)
      setSubmitting(true)
      await createPosition({ ...values, skill_requirements: skillReq })
      message.success('创建成功')
      setOpen(false)
      form.resetFields()
      load(1)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  // 单条删除
  const handleDelete = async (id: number) => {
    try {
      await deletePosition(id)
      message.success('已删除')
      load()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  // 打开编辑
  const openEdit = (record: any) => {
    setEditing(record)
    editForm.setFieldsValue({
      position_name: record.position_name,
      position_category: record.position_category,
      position_level: record.position_level,
      department_id: record.department_id,
      headcount: record.headcount,
      education_requirement: record.education_requirement,
      experience_requirement: record.experience_requirement,
      skill_requirements: (record.skill_requirements || []).join(','),
      job_description: record.job_description,
    })
    setEditOpen(true)
  }

  const handleEdit = async () => {
    if (!editing) return
    try {
      const values = await editForm.validateFields()
      const skillReq = (values.skill_requirements || '').split(',').map((s: string) => s.trim()).filter(Boolean)
      setSubmitting(true)
      await updatePosition(editing.id, { ...values, skill_requirements: skillReq })
      message.success('更新成功')
      setEditOpen(false)
      load()
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '更新失败')
    } finally {
      setSubmitting(false)
    }
  }

  // 查看详情
  const openDetail = (record: any) => {
    setDetail(record)
    setDetailOpen(true)
  }

  // 批量删除（整页删除）
  const [batchDeleting, setBatchDeleting] = useState(false)
  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选要删除的岗位')
      return
    }
    try {
      setBatchDeleting(true)
      const res = await batchDeletePositions(selectedRowKeys.map((k) => Number(k)))
      message.success(`批量删除成功：共删除 ${res?.deleted ?? selectedRowKeys.length} 条`)
      setSelectedRowKeys([])
      load()
    } catch (e: any) {
      message.error(e.message || '批量删除失败')
    } finally {
      setBatchDeleting(false)
    }
  }

  const columns = [
    { title: '编号', dataIndex: 'position_code', key: 'position_code', width: 120 },
    { title: '岗位名称', dataIndex: 'position_name', key: 'position_name' },
    { title: '类别', dataIndex: 'position_category', key: 'position_category', width: 120 },
    {
      title: '层级', dataIndex: 'position_level', key: 'position_level', width: 100,
      render: (v: string) => v ? <Tag>{LEVEL_LABEL[v] || v}</Tag> : '-',
    },
    { title: '编制', dataIndex: 'headcount', key: 'headcount', width: 80 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => {
        const cfg = STATUS_TAG[v] || { color: 'default', text: v || '-' }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    { title: '学历要求', dataIndex: 'education_requirement', key: 'education_requirement', width: 100 },
    {
      title: '经验要求(年)', dataIndex: 'experience_requirement', key: 'experience_requirement', width: 110,
      render: (v: number) => v ?? 0,
    },
    {
      title: '操作', key: 'action', width: 150, fixed: 'right' as const,
      render: (_: any, r: any) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDetail(r)}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="确定删除该岗位？" onConfirm={() => handleDelete(r.id)} okText="删除" cancelText="取消">
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><SolutionOutlined /> 岗位管理</Space>
      </Typography.Title>

      <ModuleBanner
        value="明确每个岗位的职责、能力门槛与任职标准，让「招什么人、用什么人」有据可依。"
        relation="岗位标准是匹配与培养的基准："
        prevLabel="人才档案"
        prevPath="/talents"
        nextLabel="岗位匹配"
        nextPath="/matching"
      />

      <Card bordered={false} size="small">
        <Row gutter={12}>
          <Col flex="220px">
            <Input
              placeholder="岗位名称/编号"
              value={search.keyword}
              onChange={(e) => setSearch({ ...search, keyword: e.target.value })}
              onPressEnter={onSearch}
              allowClear
            />
          </Col>
          <Col flex="140px">
            <Select
              placeholder="层级"
              value={search.position_level || undefined}
              onChange={(v) => setSearch({ ...search, position_level: v || '' })}
              options={LEVEL_OPTIONS}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col flex="120px">
            <Select
              placeholder="状态"
              value={search.status || undefined}
              onChange={(v) => setSearch({ ...search, status: v || '' })}
              options={Object.entries(STATUS_TAG).map(([k, v]) => ({ value: k, label: v.text }))}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={onSearch}>搜索</Button>
              <Button onClick={onReset}>重置</Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card bordered={false}>
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新增岗位</Button>
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
          <Button
            danger
            icon={<DeleteOutlined />}
            disabled={selectedRowKeys.length === 0}
            loading={batchDeleting}
            onClick={handleBatchDelete}
          >
            批量删除{selectedRowKeys.length > 0 ? ` (${selectedRowKeys.length})` : ''}
          </Button>
          <Badge count={total} overflowCount={9999} style={{ backgroundColor: '#f59e0b' }} />
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          columns={columns}
          scroll={{ x: 1000 }}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
            preserveSelectedRowKeys: false,
          }}
          pagination={{
            total,
            current: page,
            pageSize,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p); setPageSize(ps); load(p, ps)
            },
          }}
        />
      </Card>

      <Modal
        title="新增岗位"
        open={open}
        onOk={handleCreate}
        onCancel={() => { setOpen(false); form.resetFields() }}
        confirmLoading={submitting}
        width={680}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="position_name" label="岗位名称" rules={[{ required: true, message: '请输入岗位名称' }]}>
                <Input placeholder="如：高级数据工程师" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="department_id" label="所属部门">
                <Select
                  placeholder="请选择部门（可选）"
                  options={orgs.map((o) => ({ value: o.id, label: o.org_name }))}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="position_category" label="岗位类别">
                <Input placeholder="如：技术/产品/运营" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="position_level" label="层级" initialValue="intermediate">
                <Select options={LEVEL_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="headcount" label="编制" initialValue={1}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="education_requirement" label="学历要求">
                <Input placeholder="如：本科" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="experience_requirement" label="经验(年)" initialValue={0}>
                <InputNumber min={0} max={40} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="skill_requirements" label="技能要求(逗号分隔)">
                <Input placeholder="如：Python,SQL,Spark" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="job_description" label="岗位职责">
                <Input.TextArea rows={3} placeholder="如：负责数据平台建设与优化..." />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 编辑岗位 Modal */}
      <Modal
        title="编辑岗位"
        open={editOpen}
        onOk={handleEdit}
        onCancel={() => { setEditOpen(false); editForm.resetFields() }}
        confirmLoading={submitting}
        width={680}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="position_name" label="岗位名称" rules={[{ required: true, message: '请输入岗位名称' }]}>
                <Input placeholder="如：高级数据工程师" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="department_id" label="所属部门">
                <Select
                  placeholder="请选择部门（可选）"
                  options={orgs.map((o) => ({ value: o.id, label: o.org_name }))}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="position_category" label="岗位类别">
                <Input placeholder="如：技术/产品/运营" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="position_level" label="层级">
                <Select options={LEVEL_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="headcount" label="编制">
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="education_requirement" label="学历要求">
                <Input placeholder="如：本科" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="experience_requirement" label="经验(年)">
                <InputNumber min={0} max={40} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="skill_requirements" label="技能要求(逗号分隔)">
                <Input placeholder="如：Python,SQL,Spark" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="job_description" label="岗位职责">
                <Input.TextArea rows={3} placeholder="如：负责数据平台建设与优化..." />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 岗位详情 Modal */}
      <Modal
        title="岗位详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={680}
      >
        {detail && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="岗位编号" span={2}>{detail.position_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="岗位名称" span={2}>{detail.position_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="岗位类别">{detail.position_category || '-'}</Descriptions.Item>
            <Descriptions.Item label="层级">
              {detail.position_level ? LEVEL_LABEL[detail.position_level] || detail.position_level : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="所属部门">
              {orgs.find((o) => o.id === detail.department_id)?.org_name || detail.department_id || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="编制">{detail.headcount ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="学历要求">{detail.education_requirement || '-'}</Descriptions.Item>
            <Descriptions.Item label="经验要求(年)">{detail.experience_requirement ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">
              {detail.status ? STATUS_TAG[detail.status]?.text || detail.status : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="技能要求" span={2}>
              {Array.isArray(detail.skill_requirements) && detail.skill_requirements.length > 0
                ? detail.skill_requirements.map((s: string) => <Tag key={s}>{s}</Tag>)
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="岗位职责" span={2}>{detail.job_description || '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </Space>
  )
}
