import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import {
  getMe,
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  UserInfo,
  LoginResult,
} from './api'

interface AuthContextValue {
  user: UserInfo | null
  loading: boolean  // 应用启动时加载 /me 的状态
  login: (username: string, password: string) => Promise<UserInfo>
  register: (payload: {
    username: string
    password: string
    real_name?: string
    email?: string
    phone?: string
  }) => Promise<UserInfo>
  logout: () => Promise<void>
  /** 是否拥有指定角色（超管自动拥有所有角色权限） */
  hasRole: (roleCode: string) => boolean
  /** 是否拥有任一角色（用于菜单可见性判断） */
  hasAnyRole: (roleCodes: string[]) => boolean
}

const AuthContext = createContext<AuthContextValue>(null as any)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  // 应用启动：如果有 token，调 /me 恢复登录态
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setLoading(false)
      return
    }
    getMe()
      .then((me) => setUser(me))
      .catch(() => {
        localStorage.removeItem('token')
      })
      .finally(() => setLoading(false))
  }, [])

  const login = async (username: string, password: string) => {
    const result: LoginResult = await apiLogin(username, password)
    localStorage.setItem('token', result.access_token)
    setUser(result.user)
    return result.user
  }

  const register = async (payload: {
    username: string
    password: string
    real_name?: string
    email?: string
    phone?: string
  }) => {
    const result: LoginResult = await apiRegister(payload)
    // 注册即登录：后端返回 token，前端直接进入登录态
    localStorage.setItem('token', result.access_token)
    setUser(result.user)
    return result.user
  }

  const logout = async () => {
    try {
      await apiLogout()
    } catch {
      // 登出接口失败不阻断前端登出
    }
    localStorage.removeItem('token')
    setUser(null)
  }

  const hasRole = (roleCode: string) => {
    if (!user) return false
    if (user.is_superuser) return true  // 超管拥有所有角色权限
    return user.roles.includes(roleCode)
  }

  const hasAnyRole = (roleCodes: string[]) => roleCodes.some(hasRole)

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, hasRole, hasAnyRole }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
