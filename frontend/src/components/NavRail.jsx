import { NavLink } from 'react-router-dom'
import { Home, FlaskConical, Activity, FolderOpen, Gamepad2, Settings } from 'lucide-react'
import logoUrl from '../assets/jubilee-powder-logo.svg'

const NAV_ITEMS = [
  { to: '/',           icon: Home,        label: 'Home'       },
  { to: '/dispensing', icon: FlaskConical, label: 'Dispensing' },
  { to: '/hardness',   icon: Activity,    label: 'Hardness'   },
  { to: '/data',       icon: FolderOpen,  label: 'Data'       },
  { to: '/manual',     icon: Gamepad2,    label: 'Manual'     },
  { to: '/settings',   icon: Settings,    label: 'Settings'   },
]

export default function NavRail() {
  return (
    <nav className="flex flex-col items-center w-[clamp(5.5rem,8vw,7.5rem)] py-3 bg-gray-900 border-r border-gray-800 shrink-0 min-h-0">
      {/* Logo stays pinned while the nav items below scroll */}
      <div className="mb-3 px-2 shrink-0">
        <img
          src={logoUrl}
          alt="Jubilee Powder"
          className="w-[clamp(2.5rem,6vh,4rem)] h-auto"
        />
      </div>

      <div className="flex flex-col items-center gap-0.5 w-full flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-1">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              [
                'flex flex-col items-center gap-1 w-full py-2 px-1 rounded-xl transition-colors shrink-0',
                isActive
                  ? 'bg-amber-400/15 text-amber-400'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800',
              ].join(' ')
            }
          >
            <Icon
              className="h-[clamp(1.75rem,4vh,2.5rem)] w-[clamp(1.75rem,4vh,2.5rem)]"
              strokeWidth={1.75}
            />
            <span className="text-[clamp(0.8125rem,1.8vh,1rem)] font-medium leading-tight">
              {label}
            </span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
