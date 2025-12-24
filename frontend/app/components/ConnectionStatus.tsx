'use client'

import { useEffect, useState, useRef } from 'react'
import { useAuth } from '../contexts/AuthContext'
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function ConnectionStatus() {
  const { user, token, fetchUser } = useAuth()
  console.log("user", token);
  const [showOverlay, setShowOverlay] = useState(false)
  const [syncingService, setSyncingService] = useState<'gmail' | 'hubspot' | null>(null)
  const [gmailSyncing, setGmailSyncing] = useState(false)
  const [hubspotSyncing, setHubspotSyncing] = useState(false)
  const [gmailSyncMode, setGmailSyncMode] = useState<'month' | 'all'>('month')
  const [hubspotSyncMode, setHubspotSyncMode] = useState<'month' | 'all'>('month')
  const hasAutoSynced = useRef(false)

  const handleConnectGoogle = () => {
    window.location.href = `${API_URL}/api/auth/google`
  }

  const handleConnectHubSpot = () => {
    if (!token) {
      alert('Please log in first')
      return
    }
    // Pass token as query parameter since window.location.href doesn't support custom headers
    window.location.href = `${API_URL}/api/auth/hubspot?token=${encodeURIComponent(token)}`
  }

  const handleSyncGmail = async (mode: 'month' | 'all' = 'month') => {
    if (!token) return
    setShowOverlay(true)
    setSyncingService('gmail')
    setGmailSyncing(true)
    setGmailSyncMode(mode)
    try {
      await axios.post(
        `${API_URL}/api/integrations/sync/gmail`,
        { sync_mode: mode },
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      )
    } catch (error) {
      alert('Failed to start Gmail sync')
      setGmailSyncing(false)
      setShowOverlay(false)
      setSyncingService(null)
    }
  }

  const handleSyncHubSpot = async (mode: 'month' | 'all' = 'month') => {
    if (!token) return
    setShowOverlay(true)
    setSyncingService('hubspot')
    setHubspotSyncing(true)
    setHubspotSyncMode(mode)
    try {
      await axios.post(
        `${API_URL}/api/integrations/sync/hubspot`,
        { sync_mode: mode },
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      )
    } catch (error) {
      alert('Failed to start HubSpot sync')
      setHubspotSyncing(false)
      setShowOverlay(false)
      setSyncingService(null)
    }
  }

  const handleDismissSync = () => {
    // Only hide overlay, keep sync status tracking
    setShowOverlay(false)
  }

  // Auto-sync on page load
  useEffect(() => {
    if (!token || !user || hasAutoSynced.current) return

    const autoSync = async () => {
      hasAutoSynced.current = true
      let syncPromises: Promise<void>[] = []

      // Auto-sync Gmail if connected (this month only)
      if (user.has_google) {
        const gmailSync = async () => {
          try {
            setGmailSyncing(true)
            setGmailSyncMode('month')
            setShowOverlay(true)
            setSyncingService('gmail')
            await axios.post(
              `${API_URL}/api/integrations/sync/gmail`,
              { sync_mode: 'month' },
              {
                headers: { Authorization: `Bearer ${token}` },
              }
            )
          } catch (error) {
            console.error('Failed to auto-sync Gmail:', error)
            setGmailSyncing(false)
          }
        }
        syncPromises.push(gmailSync())
      }

      // Auto-sync HubSpot if connected (this month only)
      if (user.has_hubspot) {
        const hubspotSync = async () => {
          try {
            setHubspotSyncing(true)
            setHubspotSyncMode('month')
            setShowOverlay(true)
            // Only set syncingService if Gmail is not syncing
            if (!user.has_google || !gmailSyncing) {
              setSyncingService('hubspot')
            }
            await axios.post(
              `${API_URL}/api/integrations/sync/hubspot`,
              { sync_mode: 'month' },
              {
                headers: { Authorization: `Bearer ${token}` },
              }
            )
          } catch (error) {
            console.error('Failed to auto-sync HubSpot:', error)
            setHubspotSyncing(false)
          }
        }
        syncPromises.push(hubspotSync())
      }

      // Wait for all syncs to be initiated
      await Promise.all(syncPromises)
    }

    // Small delay to ensure UI is ready
    const timer = setTimeout(autoSync, 500)
    return () => clearTimeout(timer)
  }, [token, user])

  // Poll sync status
  useEffect(() => {
    if (!token || !user) return

    const pollSyncStatus = async () => {
      try {
        const response = await axios.get(
          `${API_URL}/api/integrations/status`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        )
        
        const gmailSyncingStatus = response.data.google?.syncing || false
        const hubspotSyncingStatus = response.data.hubspot?.syncing || false
        
        setGmailSyncing(gmailSyncingStatus)
        setHubspotSyncing(hubspotSyncingStatus)
        
        // Hide overlay when sync completes
        if (showOverlay && !gmailSyncingStatus && !hubspotSyncingStatus) {
          setShowOverlay(false)
          setSyncingService(null)
          // Refresh user data to get updated connection status (in case tokens were cleared)
          await fetchUser()
        }
      } catch (error) {
        console.error('Failed to fetch sync status:', error)
      }
    }

    // Poll every 2 seconds if any sync is in progress
    let interval: NodeJS.Timeout | null = null
    if (gmailSyncing || hubspotSyncing) {
      pollSyncStatus() // Initial check
      interval = setInterval(pollSyncStatus, 2000)
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [token, user, gmailSyncing, hubspotSyncing, showOverlay, fetchUser])

  return (
    <>
      {/* Loading Overlay */}
      {showOverlay && (gmailSyncing || hubspotSyncing) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="bg-white rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
            <div className="flex flex-col items-center">
              {/* Spinner */}
              <div className="relative w-16 h-16 mb-4">
                <div className="absolute inset-0 border-4 border-blue-200 rounded-full"></div>
                <div className="absolute inset-0 border-4 border-blue-600 rounded-full border-t-transparent animate-spin"></div>
              </div>
              
              {/* Message */}
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                {gmailSyncing && hubspotSyncing 
                  ? `Syncing Gmail & HubSpot${(gmailSyncMode === 'all' || hubspotSyncMode === 'all') ? ' (All)' : ' (This Month)'}...`
                  : syncingService === 'gmail' 
                    ? `Syncing Gmail${gmailSyncMode === 'all' ? ' (All)' : ' (This Month)'}...`
                    : `Syncing HubSpot${hubspotSyncMode === 'all' ? ' (All)' : ' (This Month)'}...`}
              </h3>
              <p className="text-sm text-gray-600 text-center mb-6">
                {gmailSyncing && hubspotSyncing
                  ? `Importing your ${(gmailSyncMode === 'all' || hubspotSyncMode === 'all') ? 'all ' : 'this month\'s '}emails and contacts. This may take a few minutes.`
                  : syncingService === 'gmail' 
                    ? `Importing your ${gmailSyncMode === 'all' ? 'all ' : 'this month\'s '}emails and creating searchable embeddings. This may take a few minutes.`
                    : `Importing your ${hubspotSyncMode === 'all' ? 'all ' : 'this month\'s '}contacts and notes. This may take a few minutes.`}
              </p>
              
              {/* Dismiss button */}
              <button
                onClick={handleDismissSync}
                className="text-sm text-gray-500 hover:text-gray-700 underline transition-colors"
              >
                Dismiss (sync continues in background)
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-4 text-sm text-gray-600">
        <span>Context set to all meetings</span>
        <span className="text-gray-400">•</span>
        <span>{new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })} - {new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
        
        <div className="flex items-center gap-4 ml-auto">
          {/* Gmail Group */}
          <div className="flex flex-col gap-1">
            <div className="text-xs text-gray-500 font-medium px-1">Gmail</div>
            {user?.has_google ? (
              <div className="flex items-center gap-3 px-4 py-2 bg-white rounded-lg border-2 border-gray-200 shadow-sm hover:border-blue-300 transition-colors">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  <span className="text-sm font-semibold text-gray-900">{user.google_email}</span>
                </div>
                <div className="h-5 w-px bg-gray-200"></div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleSyncGmail('month')}
                    disabled={gmailSyncing}
                    className={`text-xs font-semibold px-3 py-1 rounded-md transition-all ${
                      gmailSyncing 
                        ? 'bg-blue-100 text-blue-700 cursor-not-allowed' 
                        : 'bg-blue-50 text-blue-600 hover:bg-blue-100 hover:text-blue-700'
                    }`}
                  >
                    {gmailSyncing && gmailSyncMode === 'month' ? 'Syncing for month...' : 'Sync for month'}
                  </button>
                  <button
                    onClick={() => handleSyncGmail('all')}
                    disabled={gmailSyncing}
                    className={`text-xs font-semibold px-3 py-1 rounded-md transition-all ${
                      gmailSyncing 
                        ? 'bg-blue-100 text-blue-700 cursor-not-allowed' 
                        : 'bg-blue-50 text-blue-600 hover:bg-blue-100 hover:text-blue-700'
                    }`}
                  >
                    {gmailSyncing && gmailSyncMode === 'all' ? 'Syncing All...' : 'Sync All'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="px-4 py-2 bg-white rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-400 transition-colors">
                <button
                  onClick={handleConnectGoogle}
                  className="text-sm font-semibold text-blue-600 hover:text-blue-700 transition-colors"
                >
                  Connect Google
                </button>
              </div>
            )}
          </div>
          
          {/* HubSpot Group */}
          <div className="flex flex-col gap-1">
            <div className="text-xs text-gray-500 font-medium px-1">HubSpot</div>
            {user?.has_hubspot ? (
              <div className="flex items-center gap-3 px-4 py-2 bg-white rounded-lg border-2 border-gray-200 shadow-sm hover:border-orange-300 transition-colors">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  <span className="text-sm font-semibold text-gray-900">{user.hubspot_name || 'HubSpot'}</span>
                </div>
                <div className="h-5 w-px bg-gray-200"></div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleSyncHubSpot('month')}
                    disabled={hubspotSyncing}
                    className={`text-xs font-semibold px-3 py-1 rounded-md transition-all ${
                      hubspotSyncing 
                        ? 'bg-orange-100 text-orange-700 cursor-not-allowed' 
                        : 'bg-orange-50 text-orange-600 hover:bg-orange-100 hover:text-orange-700'
                    }`}
                  >
                    {hubspotSyncing && hubspotSyncMode === 'month' ? 'Syncing for month...' : 'Sync for month'}
                  </button>
                  <button
                    onClick={() => handleSyncHubSpot('all')}
                    disabled={hubspotSyncing}
                    className={`text-xs font-semibold px-3 py-1 rounded-md transition-all ${
                      hubspotSyncing 
                        ? 'bg-orange-100 text-orange-700 cursor-not-allowed' 
                        : 'bg-orange-50 text-orange-600 hover:bg-orange-100 hover:text-orange-700'
                    }`}
                  >
                    {hubspotSyncing && hubspotSyncMode === 'all' ? 'Syncing All...' : 'Sync All'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="px-4 py-2 bg-white rounded-lg border-2 border-dashed border-gray-300 hover:border-orange-400 transition-colors">
                <button
                  onClick={handleConnectHubSpot}
                  className="text-sm font-semibold text-orange-600 hover:text-orange-700 transition-colors"
                >
                  Connect HubSpot
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

