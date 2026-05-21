import React from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { RefreshCw, X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'

const PWAReloadPrompt: React.FC = () => {
  const {
    offlineReady: [offlineReady, setOfflineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(r: ServiceWorkerRegistration | undefined) {
      console.log('SW Registered: ' + r)
    },
    onRegisterError(error: any) {
      console.log('SW registration error', error)
    },
  })

  const close = () => {
    setOfflineReady(false)
    setNeedRefresh(false)
  }

  return (
    <AnimatePresence>
      {(offlineReady || needRefresh) && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          className="fixed bottom-4 right-4 z-50 p-4 bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl max-w-sm"
        >
          <div className="flex flex-col gap-3">
            <div className="flex items-start justify-between gap-4">
              <div className="text-sm text-zinc-300">
                {offlineReady ? (
                  <span>App ready to work offline</span>
                ) : (
                  <span>New content available, click on reload button to update.</span>
                )}
              </div>
              <button
                onClick={close}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <X size={18} />
              </button>
            </div>
            {needRefresh && (
              <button
                onClick={() => updateServiceWorker(true)}
                className="flex items-center justify-center gap-2 w-full py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium transition-colors text-sm"
              >
                <RefreshCw size={16} />
                Reload
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default PWAReloadPrompt
