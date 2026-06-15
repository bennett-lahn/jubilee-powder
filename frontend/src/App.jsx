import { useCallback, useEffect, useState } from 'react'
import { createBrowserRouter, RouterProvider, Outlet } from 'react-router-dom'

import { useJubileeStore } from './store/jubileeStore'
import NavRail from './components/NavRail'
import BottomBar from './components/BottomBar'
import Dialog from './components/ui/Dialog'
import Button from './components/ui/Button'

import HomeScreen             from './screens/HomeScreen'
import PowderDispensingScreen from './screens/PowderDispensingScreen'
import HardnessTestingScreen  from './screens/HardnessTestingScreen'
import DataScreen             from './screens/DataScreen'
import ManualControlScreen    from './screens/ManualControlScreen'
import SettingsScreen         from './screens/SettingsScreen'

// Root layout — nav rail + main content area + bottom status bar.
// Wraps every route so navigation and telemetry are always visible.
function RootLayout() {
  const connectWs          = useJubileeStore((s) => s.connectWs)
  const disconnectWs       = useJubileeStore((s) => s.disconnectWs)
  const telemetry          = useJubileeStore((s) => s.telemetry)
  const clearJam           = useJubileeStore((s) => s.clearJam)
  const errorDialog        = useJubileeStore((s) => s.errorDialog)
  const dismissErrorDialog = useJubileeStore((s) => s.dismissErrorDialog)
  const [jamClearing, setJamClearing] = useState(false)

  const job = telemetry.job
  const jamDetected = (telemetry.state === 'running') && (job?.jam_detected ?? false)
  const jamWellId = job?.jam_well_id ?? null

  const handleClearJam = useCallback(async () => {
    setJamClearing(true)
    await clearJam()
    setJamClearing(false)
  }, [clearJam])

  useEffect(() => {
    connectWs()
    return () => disconnectWs()
  }, [])

  return (
    <div className="flex flex-col h-screen w-screen bg-slate-900 text-white overflow-hidden">
      <div className="flex flex-1 overflow-hidden min-h-0">
        <NavRail />
        {/* overflow-hidden + min-h-0 lets child screens use h-full to fill */}
        <main className="flex-1 overflow-hidden min-h-0 p-4">
          <Outlet />
        </main>
      </div>
      <BottomBar />

      {/* Global error dialog — surfaces whenever the machine enters ERROR state */}
      <Dialog
        open={errorDialog.open}
        title="Error"
        onClose={dismissErrorDialog}
        footer={
          <Button variant="danger" onClick={dismissErrorDialog}>
            Dismiss
          </Button>
        }
      >
        <p className="text-slate-300 text-sm whitespace-pre-wrap leading-relaxed">
          {errorDialog.message}
        </p>
      </Dialog>

      {/* Global jam intervention dialog - consistent with global error policy */}
      <Dialog
        open={jamDetected}
        title="Powder Flow Jam"
        footer={
          <Button
            variant="filled"
            onClick={handleClearJam}
            disabled={jamClearing}
          >
            {jamClearing ? 'Resuming...' : 'Blockage Cleared - Resume'}
          </Button>
        }
      >
        <p className="text-sm text-slate-300 mb-2">
          Powder flow has stalled{jamWellId != null
            ? <> on well <span className="font-semibold text-slate-100">{jamWellId}</span></>
            : null
          }.
        </p>
        <p className="text-sm text-slate-400 mb-2">
          Clear the blockage in the trickler hopper, then press the button below
          to resume dispensing.
        </p>
        <p className="text-xs text-slate-500">
          To abandon this job entirely, use the Cancel or Abort buttons instead.
        </p>
      </Dialog>
    </div>
  )
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      { index: true,          element: <HomeScreen />             },
      { path: 'dispensing',   element: <PowderDispensingScreen /> },
      { path: 'hardness',     element: <HardnessTestingScreen />  },
      { path: 'data',         element: <DataScreen />             },
      { path: 'manual',       element: <ManualControlScreen />    },
      { path: 'settings',     element: <SettingsScreen />         },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
