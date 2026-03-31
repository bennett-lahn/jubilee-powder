/**
 * Data Browser Screen.
 *
 * Ports the Kivy DataScreen.
 * Lists files from the backend data directory via GET /api/files.
 * Falls back gracefully when the endpoint is not yet implemented.
 */

import { useState, useEffect } from 'react'
import { FileText, Image, FileSpreadsheet, Folder, RefreshCw, FolderOpen } from 'lucide-react'
import { Button, Card, StatusBadge } from '../components/ui'

const ICON_MAP = {
  '.csv':  FileSpreadsheet,
  '.json': FileText,
  '.txt':  FileText,
  '.png':  Image,
  '.jpg':  Image,
  '.jpeg': Image,
  '.pdf':  FileText,
  '.xlsx': FileSpreadsheet,
}

function fileIcon(name) {
  if (!name) return FileText
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
  return ICON_MAP[ext] ?? FileText
}

function formatSize(bytes) {
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes
  for (const u of units) {
    if (n < 1024) return `${n.toFixed(1)} ${u}`
    n /= 1024
  }
  return `${n.toFixed(1)} TB`
}

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function DataScreen() {
  const [files, setFiles]     = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  async function loadFiles() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/files')
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      setFiles(await res.json())
    } catch (e) {
      setError(e.message)
      setFiles([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadFiles() }, [])

  return (
    <div className="flex flex-col gap-4 h-full">

      {/* Header toolbar */}
      <Card className="flex items-center gap-4 p-4 shrink-0">
        <FolderOpen size={20} className="text-slate-400" />
        <span className="text-slate-300 font-medium">Data Browser</span>
        <div className="flex-1" />
        <Button variant="ghost" size="sm" onClick={loadFiles}>
          <RefreshCw size={14} className="mr-2" />
          Refresh
        </Button>
      </Card>

      {/* File list */}
      <Card className="flex-1 overflow-y-auto p-2">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <p className="text-slate-500 text-sm">Loading files…</p>
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <StatusBadge status="error" label="Could not load files" />
            <p className="text-xs text-slate-600">{error}</p>
          </div>
        )}

        {!loading && !error && files.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <p className="text-slate-500 text-sm">No files in data directory.</p>
          </div>
        )}

        {!loading && !error && files.length > 0 && (
          <ul className="divide-y divide-slate-700/50">
            {files.map((f) => {
              const Icon = f.type === 'folder' ? Folder : fileIcon(f.name)
              return (
                <li key={f.name}>
                  <button
                    className="w-full flex items-center gap-4 px-4 py-3 rounded-xl hover:bg-slate-700/50 text-left transition-colors"
                    onClick={() => {/* TODO: POST /api/files/open with f.path */}}
                  >
                    <Icon size={20} className="text-slate-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-200 truncate">{f.name}</p>
                      {f.type !== 'folder' && (
                        <p className="text-xs text-slate-500">
                          {formatSize(f.size)} &middot; {formatDate(f.modified)}
                        </p>
                      )}
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </div>
  )
}
