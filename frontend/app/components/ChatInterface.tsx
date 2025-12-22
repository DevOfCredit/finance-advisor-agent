'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import ConnectionStatus from './ConnectionStatus'
import axios from 'axios'

interface Message {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  error?: boolean
  timestamp: Date
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function ChatInterface() {
  const { user, token, loading } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [hasMoreHistory, setHasMoreHistory] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const isLoadingMoreRef = useRef(false)

  // Load initial chat history (15-20 messages)
  useEffect(() => {
    if (!user || !token) return

    const loadInitialHistory = async () => {
      try {
        setIsLoadingHistory(true)
        const response = await axios.get(
          `${API_URL}/api/chat/history`,
          {
            params: { limit: 20 },
            headers: { Authorization: `Bearer ${token}` },
          }
        )

        const historyMessages: Message[] = response.data.messages.map((msg: any) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          error: msg.error,
          timestamp: new Date(msg.timestamp),
        }))

        // Sort by timestamp (oldest first) to ensure proper chronological order
        historyMessages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
        
        setMessages(historyMessages)
        setHasMoreHistory(response.data.has_more)

        // Scroll to bottom after loading history
        setTimeout(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: 'auto' })
        }, 100)
      } catch (error) {
        console.error('Failed to load chat history:', error)
        // If no history, show initial welcome message
        if (messages.length === 0) {
          setMessages([
            {
              id: 'welcome',
              role: 'assistant',
              content: "I can answer questions about any Jump meeting. What do you want to know?",
              timestamp: new Date(),
            },
          ])
        }
      } finally {
        setIsLoadingHistory(false)
      }
    }

    loadInitialHistory()
  }, [user, token])

  // Auto-scroll to bottom when new messages arrive (but not when loading history)
  useEffect(() => {
    if (!isLoadingHistory) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isLoadingHistory])

  // Infinite scroll: load older messages when scrolling to top
  const loadOlderMessages = useCallback(async () => {
    if (!token || !hasMoreHistory || isLoadingMoreRef.current || messages.length === 0) return

    // Find the oldest message ID (first message in the array)
    const oldestMessage = messages[0]
    if (typeof oldestMessage.id !== 'number') return

    // Store current scroll position and height before loading
    const container = messagesContainerRef.current
    const scrollHeightBefore = container?.scrollHeight || 0
    const scrollTopBefore = container?.scrollTop || 0

    isLoadingMoreRef.current = true
    try {
      const response = await axios.get(
        `${API_URL}/api/chat/history`,
        {
          params: { limit: 20, before_id: oldestMessage.id },
          headers: { Authorization: `Bearer ${token}` },
        }
      )

      if (response.data.messages.length > 0) {
        const olderMessages: Message[] = response.data.messages.map((msg: any) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          error: msg.error,
          timestamp: new Date(msg.timestamp),
        }))

        // Sort by timestamp (oldest first)
        olderMessages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())

        // Prepend older messages to existing messages
        setMessages((prev) => {
          const combined = [...olderMessages, ...prev]
          // Sort again to ensure proper order
          combined.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
          return combined
        })
        setHasMoreHistory(response.data.has_more)

        // Restore scroll position after new content is loaded
        setTimeout(() => {
          if (container) {
            const scrollHeightAfter = container.scrollHeight
            const heightDifference = scrollHeightAfter - scrollHeightBefore
            container.scrollTop = scrollTopBefore + heightDifference
          }
        }, 50)
      } else {
        setHasMoreHistory(false)
      }
    } catch (error) {
      console.error('Failed to load older messages:', error)
    } finally {
      isLoadingMoreRef.current = false
    }
  }, [token, hasMoreHistory, messages])

  // Handle scroll event for infinite scroll
  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container || !hasMoreHistory) return

    let lastScrollTop = container.scrollTop
    let ticking = false

    const handleScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const currentScrollTop = container.scrollTop
          
          // Only trigger if scrolling up (not down) and near the top
          if (
            currentScrollTop < lastScrollTop && // Scrolling up
            currentScrollTop < 500 && // Within 500px of top
            hasMoreHistory && 
            !isLoadingMoreRef.current
          ) {
            loadOlderMessages()
          }
          
          lastScrollTop = currentScrollTop
          ticking = false
        })
        ticking = true
      }
    }

    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => container.removeEventListener('scroll', handleScroll)
  }, [hasMoreHistory, loadOlderMessages])

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || !token) return

    // Add user message optimistically
    const userMessage: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)

    try {
      // Convert messages to API format (only user and assistant messages, no temp IDs)
      const conversationHistory = messages
        .filter((msg) => typeof msg.id === 'number' || !msg.id.toString().startsWith('temp-'))
        .map((msg) => ({
          role: msg.role,
          content: msg.content,
        }))

      // Send to API
      const response = await axios.post(
        `${API_URL}/api/chat/`,
        {
          message: content,
          conversation_history: conversationHistory,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      )

      // Replace temp user message with real one (if API returns it, otherwise keep temp)
      // Add assistant response with real ID from database
      const assistantMessage: Message = {
        id: response.data.message_id || `temp-${Date.now() + 1}`,
        role: 'assistant',
        content: response.data.response || 'No response received',
        error: !!response.data.error,
        timestamp: new Date(),
      }

      if (response.data.error) {
        assistantMessage.content = `Error: ${response.data.error}`
        assistantMessage.error = true
      }

      // Update messages: replace temp user message and add assistant message
      setMessages((prev) => {
        const updated = [...prev]
        // Replace the last message (temp user message) with real user message
        updated[updated.length - 1] = {
          ...userMessage,
          id: `temp-${Date.now()}` // Keep temp ID for now, will be replaced on reload
        }
        const newMessages = [...updated, assistantMessage]
        // Sort by timestamp to ensure proper order
        newMessages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
        return newMessages
      })
    } catch (error: any) {
      // Add error message
      const errorMessage: Message = {
        id: `temp-${Date.now() + 1}`,
        role: 'assistant',
        content: `Error: ${error.response?.data?.detail || error.message || 'Failed to send message'}`,
        error: true,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gradient-to-br from-blue-50 to-white">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
          <div className="text-gray-600 font-medium">Loading...</div>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="flex items-center justify-center h-screen bg-gradient-to-br from-blue-50 via-white to-gray-50">
        <div className="text-center max-w-md px-6">
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center shadow-xl">
            <svg className="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Financial Advisor AI Agent</h1>
          <p className="text-gray-600 mb-8">Connect your accounts to get started</p>
          <a
            href={`${API_URL}/api/auth/google`}
            className="inline-flex items-center gap-3 px-6 py-3 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 active:bg-blue-800 shadow-lg hover:shadow-xl transition-all transform hover:scale-105"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Log in with Google
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-gradient-to-b from-gray-50 to-white">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center shadow-sm">
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">Ask Anything</h1>
                <p className="text-xs text-gray-500">AI-powered assistant for your meetings</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Connection Status */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="px-6 py-3 max-w-7xl mx-auto">
          <ConnectionStatus />
        </div>
      </div>

      {/* Chat Messages */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto px-6 py-6 bg-gradient-to-b from-gray-50 via-white to-gray-50"
      >
        {isLoadingHistory && messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
              <div className="text-sm text-gray-500">Loading chat history...</div>
            </div>
          </div>
        )}
        <div className="max-w-4xl mx-auto space-y-6">
          {isLoadingMoreRef.current && (
            <div className="flex justify-center py-4">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></div>
                Loading older messages...
              </div>
            </div>
          )}
          {hasMoreHistory && messages.length > 0 && !isLoadingMoreRef.current && (
            <div className="flex justify-center py-2">
              <button
                onClick={loadOlderMessages}
                className="text-sm font-medium text-gray-500 hover:text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors"
              >
                Load older messages
              </button>
            </div>
          )}
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          {isLoading && (
            <div className="flex items-center gap-2 text-gray-500 pl-11">
              <div className="flex gap-1.5">
                <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm ml-2">Thinking...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Chat Input */}
      <div className="bg-white border-t border-gray-200 shadow-lg">
        <div className="px-6 py-4 max-w-7xl mx-auto">
          <ChatInput onSend={handleSendMessage} disabled={isLoading} />
        </div>
      </div>
    </div>
  )
}
