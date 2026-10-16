import { useEffect, useState } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, message, Space, Card, Tag, Row, Col,
  Typography, Badge, Popconfirm, Tooltip, Divider,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, EditOutlined,
  KeyOutlined, PoweroffOutlined, CrownOutlined, UserSwitchOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listUsers, createUser, updateUser, toggleUserStatus, resetUserPassword, deleteUser, listRoles,
  type UserItem, type RoleItem,
} from '../api'
import { useAuth } from '../AuthContext'

// 角色 code → 显示配置（与 MainLayout 保持一致）
const ROLE_LABELS: Record<string, string> = {
  super_admin: '超级管理员',
  admin: '管理员',
  hr: 'HR专员',
  user: '普通用户',
}
const ROLE_COLORS: Record<string, string> = {
  super_admin: 'red',
  admin: 'orange',
  hr: 'blue',
  user: 'default',
}
const STATUS_TAG: Record<string, { color: string; text: string }> = {
  active: { color: 'green', text: '正常' },
  inactive: { color: 'default', text: '停用' },
  locked: { color: 'red', text: '锁定' },
}

export default function UserList() {
  const { user: currentAuthUser } = useAuth()
  const currentUsername = currentAuthUser?.username || ''
  const [data, setData] = useState<UserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [search, setSearch] = useState({ keyword: '', role_code: '', status: '' })

  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [pwdOpen, setPwdOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [current, setCurrent] = useState<UserItem | null>(null)
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [pwdForm] = Form.useForm()

  const load = async (p = page, ps = pageSize, filters = search) => {
    setLoading(true)
    try {
      const res = await listUsers({ page: p, page_size: ps, ...filters })
      setData(res.items || [])
      setTotal(res.total || 0)
    } catch (e: any) {
      message.error(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  const loadRoles = async () => {
    try {
      const list = await listRoles()
      setRoles(list || [])
    } catch (e: any) {
      // 角色加载失败不阻断主流程
      console.error('角色加载失败', e)
    }
  }

  useEffect(() => {
    load(1, 10, search)
    loadRoles()
  }, [])  // eslint-disable-line

  const onSearch = () => {
    setPage(1)
    load(1, pageSize, search)
  }

  const onReset = () => {
    const empty = { keyword: '', role_code: '', status: '' }
    setSearch(empty)
    setPage(1)
    load(1, pageSize, empty)
  }

  // 新建用户
  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields()
      setSubmitting(true)
      await createUser(values)
      message.success('用户创建成功')
      setCreateOpen(false)
      createForm.resetFields()
      load(1)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  // 打开编辑
  const openEdit = (record: UserItem) => {
    setCurrent(record)
    editForm.setFieldsValue({
      real_name: record.real_name,
      email: record.email,
      phone: record.phone,
      role_code: record.roles?.[0] || 'user',
    })
    setEditOpen(true)
  }

  const handleEdit = async () => {
    if (!current) return
    try {
      const values = await editForm.validateFields()
      setSubmitting(true)
      await updateUser(current.id, values)
      message.success('用户更新成功')
      setEditOpen(false)
      load()
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '更新失败')
    } finally {
      setSubmitting(false)
    }
  }

  // 启停
  const handleToggle = async (record: UserItem) => {
    try {
      await toggleUserStatus(record.id)
      message.success('状态已切换')
      load()
    } catch (e: any) {
      message.error(e.message || '操作失败')
    }
  }

  // 删除
  const handleDelete = async (record: UserItem) => {
    try {
      const res = await deleteUser(record.id)
      message.success((res as any)?.message || `已删除用户 ${record.username}`)
      load()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  // 打开重置密码
  const openPwd = (record: UserItem) => {
    setCurrent(record)
    pwdForm.resetFields()
    setPwdOpen(true)
  }

  const handleResetPwd = async () => {
    if (!current) return
    try {
      const values = await pwdForm.validateFields()
      setSubmitting(true)
      await resetUserPassword(current.id, values.new_password)
      message.success('密码已重置')
      setPwdOpen(false)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '重置失败')
    } finally {
      setSubmitting(false)
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '用户名', dataIndex: 'username', key: 'username', width: 120 },
    { title: '姓名', dataIndex: 'real_name', key: 'real_name', width: 100, render: (v: string) => v || '-' },
    { title: '邮箱', dataIndex: 'email', key: 'email', ellipsis: true, render: (v: string) => v || '-' },
    { title: '手机号', dataIndex: 'phone', key: 'phone', width: 130, render: (v: string) => v || '-' },
    {
      title: '角色', dataIndex: 'roles', key: 'roles', width: 140,
      render: (roles: string[]) => (
        <Space size={4} wrap>
          {roles && roles.length > 0
            ? roles.map((r) => (
              <Tag key={r} color={ROLE_COLORS[r] || 'default'}>{ROLE_LABELS[r] || r}</Tag>
            ))
            : <Tag>无</Tag>}
        </Space>
      ),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => {
        const cfg = STATUS_TAG[v] || { color: 'default', text: v || '-' }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '超管', dataIndex: 'is_superuser', key: 'is_superuser', width: 80,
      render: (v: boolean) => v ? <CrownOutlined style={{ color: '#f59e0b' }} /> : '-',
    },
    {
      title: '最后登录', dataIndex: 'last_login_time', key: 'last_login_time', width: 170,
      render: (v: string, r: UserItem) => {
        if (!v) {
          return (
            <Tooltip title={`该用户尚未登录过系统${r.login_count ? `（累计 ${r.login_count} 次）` : ''}`}>
              <span style={{ color: 'rgba(0,0,0,0.35)', fontStyle: 'italic' }}>从未登录</span>
            </Tooltip>
          )
        }
        const d = dayjs(v)
        const diffDays = dayjs().diff(d, 'day')
        return (
          <Tooltip title={d.format('YYYY-MM-DD HH:mm:ss')}>
            <span>
              {d.format('YYYY-MM-DD HH:mm')}
              {diffDays <= 0 && <span style={{ marginLeft: 6, color: '#52c41a', fontSize: 11 }}>● 今天</span>}
              {diffDays > 0 && diffDays <= 3 && <span style={{ marginLeft: 6, color: '#faad14', fontSize: 11 }}>{diffDays}天前</span>}
              {diffDays > 3 && <span style={{ marginLeft: 6, color: 'rgba(0,0,0,0.35)', fontSize: 11 }}>{diffDays}天前</span>}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作', key: 'action', width: 240, fixed: 'right' as const,
      render: (_: any, r: UserItem) => {
        // 不可删除：自己 / 其他超管（前端友好提示，后端有强校验兜底）
        const isSelf = r.username === currentUsername
        const isProtected = r.is_superuser
        const cannotDelete = isSelf || isProtected
        const deleteTip = isSelf ? '不能删除自己' : isProtected ? '超管账号不可删除' : '删除用户'
        return (
          <Space size={0}>
            <Tooltip title="编辑">
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
            </Tooltip>
            <Tooltip title={r.status === 'active' ? '停用' : '启用'}>
              <Popconfirm
                title={r.status === 'active' ? '确定停用该用户？' : '确定启用该用户？'}
                onConfirm={() => handleToggle(r)}
                okText="确定"
                cancelText="取消"
                disabled={isSelf}
              >
                <Button type="link" size="small" icon={<PoweroffOutlined />} disabled={isSelf} />
              </Popconfirm>
            </Tooltip>
            <Tooltip title="重置密码">
              <Button type="link" size="small" icon={<KeyOutlined />} onClick={() => openPwd(r)} disabled={isSelf} />
            </Tooltip>
            <Tooltip title={deleteTip}>
              <Popconfirm
                title={`确定删除用户「${r.username}」？`}
                description="该操作不可恢复，将同时删除其角色关联。"
                onConfirm={() => handleDelete(r)}
                okText="确定删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                disabled={cannotDelete}
              >
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={cannotDelete}
                />
              </Popconfirm>
            </Tooltip>
          </Space>
        )
      },
    },
  ]

  // 角色选项（从后端加载，缺失则用默认）
  const roleOptions = roles.length > 0
    ? roles.map((r) => ({ value: r.role_code, label: r.role_name }))
    : Object.entries(ROLE_LABELS).map(([k, v]) => ({ value: k, label: v }))

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><UserSwitchOutlined /> 用户管理</Space>
      </Typography.Title>

      <Card bordered={false} size="small">
        <Row gutter={12}>
          <Col flex="220px">
            <Input
              placeholder="用户名/姓名/手机/邮箱"
              value={search.keyword}
              onChange={(e) => setSearch({ ...search, keyword: e.target.value })}
              onPressEnter={onSearch}
              allowClear
            />
          </Col>
          <Col flex="160px">
            <Select
              placeholder="角色"
              value={search.role_code || undefined}
              onChange={(v) => setSearch({ ...search, role_code: v || '' })}
              options={roleOptions}
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新增用户</Button>
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
          <Badge count={total} overflowCount={9999} style={{ backgroundColor: '#ef4444' }} />
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          columns={columns}
          scroll={{ x: 1200 }}
          pagination={{
            total,
            current: page,
            pageSize,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 个用户`,
            onChange: (p, ps) => {
              setPage(p); setPageSize(ps); load(p, ps)
            },
          }}
        />
      </Card>

      {/* 新增用户 Modal */}
      <Modal
        title="新增用户"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); createForm.resetFields() }}
        confirmLoading={submitting}
        width={600}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" preserve={false} initialValues={{ role_code: 'user' }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }, { min: 3, message: '至少 3 个字符' }]}>
                <Input placeholder="如：zhangsan" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }, { min: 12, message: '至少 12 位' }]}>
                <Input.Password placeholder="≥ 6 位" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="real_name" label="真实姓名">
                <Input placeholder="如：张三" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="role_code" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
                <Select options={roleOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
                <Input placeholder="如：zhangsan@example.com" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="phone" label="手机号">
                <Input placeholder="如：13800138000" />
              </Form.Item>
            </Col>
          </Row>
          <Divider style={{ margin: '8px 0 16px' }} />
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
            提示：创建后用户初始状态为「正常」，可后续启用/停用。密码将以哈希方式存储，不可逆。
          </Typography.Paragraph>
        </Form>
      </Modal>

      {/* 编辑用户 Modal */}
      <Modal
        title={`编辑用户：${current?.username || ''}`}
        open={editOpen}
        onOk={handleEdit}
        onCancel={() => setEditOpen(false)}
        confirmLoading={submitting}
        width={520}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item name="real_name" label="真实姓名">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input />
          </Form.Item>
          <Form.Item name="role_code" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select options={roleOptions} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码 Modal */}
      <Modal
        title={`重置密码：${current?.username || ''}`}
        open={pwdOpen}
        onOk={handleResetPwd}
        onCancel={() => setPwdOpen(false)}
        confirmLoading={submitting}
        width={440}
        okText="重置"
        cancelText="取消"
      >
        <Form form={pwdForm} layout="vertical" preserve={false}>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 12, message: '至少 12 位' },
            ]}
          >
            <Input.Password placeholder="≥ 6 位" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                  return Promise.reject(new Error('两次密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password placeholder="再输入一次" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
