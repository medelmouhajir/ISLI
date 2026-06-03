import { useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { KeyRound, Terminal } from 'lucide-react'

export function LoginPage() {
  const { login } = useAuth()
  const [value, setValue] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) {
      setError('API key is required')
      return
    }
    login(trimmed)
    setValue('')
    setError('')
  }

  return (
    <div className="min-h-screen bg-[#0A0014] text-[#00FF41] font-mono flex items-center justify-center p-4 relative overflow-hidden select-none">
      {/* Google Fonts Import */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&display=swap');
        
        .crt-scanlines::before {
          content: " ";
          display: block;
          position: absolute;
          top: 0;
          left: 0;
          bottom: 0;
          right: 0;
          background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06));
          z-index: 100;
          background-size: 100% 4px, 3px 100%;
          pointer-events: none;
        }

        .crt-flicker {
          animation: flicker 0.15s infinite;
        }

        @keyframes flicker {
          0% { opacity: 0.98; }
          5% { opacity: 0.95; }
          10% { opacity: 0.9; }
          15% { opacity: 0.98; }
          20% { opacity: 0.95; }
          25% { opacity: 0.98; }
          30% { opacity: 0.9; }
          100% { opacity: 1; }
        }

        .neon-text {
          text-shadow: 0 0 10px #00FF41;
        }

        .neon-border {
          box-shadow: 0 0 15px rgba(0, 255, 65, 0.3), inset 0 0 15px rgba(0, 255, 65, 0.3);
          border: 1px solid #00FF41;
        }
      `}</style>

      {/* Background Effect */}
      <div className="absolute inset-0 crt-scanlines pointer-events-none opacity-40"></div>

      <div className="max-w-md w-full z-10 space-y-8 crt-flicker">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full neon-border bg-[#0A0014] mb-4">
            <Terminal className="w-8 h-8" />
          </div>
          <h1 className="text-3xl font-bold tracking-tighter neon-text uppercase">System Access</h1>
          <p className="text-sm opacity-70">Authenticated session required for admin operations.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-[0.2em] font-bold">Admin API Key</label>
            <div className="relative">
              <input
                type="password"
                placeholder="Enter Credentials"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                autoFocus
                className="w-full bg-black/50 border border-[#00FF41]/30 p-4 rounded-none focus:outline-none focus:border-[#00FF41] focus:ring-1 focus:ring-[#00FF41] transition-all placeholder:text-[#00FF41]/20 text-[#00FF41]"
              />
            </div>
          </div>

          {error && (
            <div className="p-3 border border-[#FFB000] bg-[#FFB000]/10 text-[#FFB000] text-xs uppercase tracking-wider animate-pulse">
              Error: {error}
            </div>
          )}

          <div className="flex flex-col gap-4">
            <button
              type="submit"
              className="w-full py-4 neon-border bg-[#00FF41]/10 hover:bg-[#00FF41]/20 text-[#00FF41] font-bold uppercase tracking-[0.3em] transition-all flex items-center justify-center gap-3 active:scale-[0.98]"
            >
              <KeyRound className="w-5 h-5" />
              Authorize
            </button>
            <p className="text-[10px] text-center opacity-40 uppercase tracking-widest">
              Security Protocol v4.2.0-LIT
            </p>
          </div>
        </form>
      </div>
    </div>
  )
}
