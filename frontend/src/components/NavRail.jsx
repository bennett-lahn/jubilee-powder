import { NavLink } from 'react-router-dom'
import { FlaskConical, Activity, FolderOpen, Gamepad2, Settings } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/',         icon: FlaskConical, label: 'Dispensing' },
  { to: '/hardness', icon: Activity,     label: 'Hardness'   },
  { to: '/data',     icon: FolderOpen,   label: 'Data'       },
  { to: '/manual',   icon: Gamepad2,     label: 'Manual'     },
  { to: '/settings', icon: Settings,     label: 'Settings'   },
]

export default function NavRail() {
  return (
    <nav className="flex flex-col items-center gap-1 w-20 py-6 bg-gray-900 border-r border-gray-800 shrink-0">
      <div className="mb-6 px-2">
        <div className="h-8 w-8 rounded-full bg-amber-400" aria-hidden="true" />
      </div>

      {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            [
              'flex flex-col items-center gap-1 w-full py-3 px-1 rounded-xl mx-1 transition-colors',
              isActive
                ? 'bg-amber-400/15 text-amber-400'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800',
            ].join(' ')
          }
        >
          <Icon size={22} strokeWidth={1.75} />
          <span className="text-[10px] font-medium leading-none">{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
