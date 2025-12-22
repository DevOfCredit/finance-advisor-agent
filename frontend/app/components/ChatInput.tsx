'use client'

import { useState, KeyboardEvent, useRef, useEffect } from 'react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    if (input.trim() && !disabled) {
      onSend(input.trim())
      setInput('')
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [input])

  const canSend = input.trim().length > 0 && !disabled

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-end gap-3 bg-white border-2 border-gray-200 rounded-xl p-3 shadow-sm focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your meetings..."
          disabled={disabled}
          className="flex-1 resize-none border-none outline-none bg-transparent text-gray-900 placeholder-gray-400 py-1.5 px-2 min-h-[24px] max-h-32 text-sm leading-6"
          rows={1}
        />
        
        <button
          onClick={handleSend}
          disabled={!canSend}
          className={`flex-shrink-0 p-2 rounded-lg transition-all ${
            canSend
              ? 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 shadow-sm'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
          }`}
          title="Send message (Enter)"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </button>
      </div>
      <p className="text-xs text-gray-400 mt-2 px-2">Press Enter to send, Shift+Enter for new line</p>
    </div>
  )
}

