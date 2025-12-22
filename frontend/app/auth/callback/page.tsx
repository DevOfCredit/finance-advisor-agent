'use client'

import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '../../contexts/AuthContext'

export default function AuthCallback() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { login, fetchUser } = useAuth()

  useEffect(() => {
    const token = searchParams.get('token')
    const hubspot = searchParams.get('hubspot')

    if (token) {
      login(token)
      router.push('/')
    } else if (hubspot === 'connected') {
      fetchUser()
      router.push('/')
    } else {
      router.push('/')
    }
  }, [searchParams, login, fetchUser, router])

  return (
    <div className="flex items-center justify-center h-screen">
      <div className="text-gray-500">Completing authentication...</div>
    </div>
  )
}

