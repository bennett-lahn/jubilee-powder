import { useEffect } from 'react'
import { createBrowserRouter, RouterProvider, Outlet } from 'react-router-dom'

import { useJubileeStore } from './store/jubileeStore'
import NavRail from './components/NavRail'
import BottomBar from './components/BottomBar'

import HomeScreen             from './screens/HomeScreen'
import PowderDispensingScreen from './screens/PowderDispensingScreen'
import HardnessTestingScreen  from './screens/HardnessTestingScreen'
import DataScreen             from './screens/DataScreen'
import ManualControlScreen    from './screens/ManualControlScreen'
import SettingsScreen         from './screens/SettingsScreen'

// Root layout — nav rail + main content area + bottom status bar.
// Wraps every route so navigation and telemetry are always visible.
function RootLayout() {
  const connectWs    = useJubileeStore((s) => s.connectWs)
  const disconnectWs = useJubileeStore((s) => s.disconnectWs)
  const loadStatus   = useJubileeStore((s) => s.loadStatus)

  useEffect(() => {
    connectWs()
    loadStatus()
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
