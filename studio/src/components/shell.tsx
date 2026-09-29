import { Link, useRouterState } from '@tanstack/react-router'
import {
  GridIcon,
  PlayIcon,
  PlusIcon,
  LaptopIcon,
  BookIcon,
  ArrowUpRightIcon,
  ChevronRightIcon,
  BranchIcon,
  ReactLogoIcon,
} from './icons'
import { ExpoLogo } from './expo-logo'

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const section =
    pathname.startsWith('/drafts') || pathname === '/new'
      ? 'Drafts'
      : pathname === '/environment'
        ? 'Environment'
        : /^\/(runs?|attempts|jobs)(\/|$)/.test(pathname)
          ? 'Runs'
          : 'Tasks'
  const links = [
    { to: '/', label: 'Tasks', Icon: GridIcon },
    { to: '/runs', label: 'Runs', Icon: PlayIcon },
    { to: '/drafts', label: 'Drafts', Icon: BookIcon },
  ] as const

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link to="/" className="brand" aria-label="Expo Evals home">
          <ExpoLogo />
          <span className="brand-product">Evals</span>
        </Link>
        <Link to="/environment" className="workspace">
          <span className="workspace-avatar">
            <ReactLogoIcon />
          </span>
          <span className="workspace-name">
            Expo Harbor<small>Local workspace</small>
          </span>
          <ChevronRightIcon />
        </Link>
        <div className="nav-label">Workspace</div>
        <nav aria-label="Main navigation">
          {links.map(({ to, label, Icon }) => (
            <Link
              key={to}
              to={to}
              className={`nav-link ${section === label ? 'active' : ''}`}
              aria-current={section === label ? 'page' : undefined}
            >
              <Icon />
              {label}
            </Link>
          ))}
        </nav>
        <Link to="/new" className="nav-link sidebar-create">
          <PlusIcon />
          Create a task
        </Link>
        <div className="sidebar-bottom">
          <div className="nav-label">Resources</div>
          <Link
            to="/environment"
            className={`nav-link ${section === 'Environment' ? 'active' : ''}`}
          >
            <LaptopIcon />
            Environment
          </Link>
          <a
            className="nav-link"
            href="https://harborframework.com/docs"
            target="_blank"
            rel="noreferrer"
          >
            <BookIcon />
            Documentation
            <ArrowUpRightIcon className="nav-external" />
          </a>
        </div>
      </aside>
      <div className="main-frame">
        <div className="content-scroll" id="content-scroll">
          <div className="topbar">
            <nav className="breadcrumbs" aria-label="Breadcrumb">
              <Link to="/">
                <BranchIcon />
                <span>expo-harbor-eval</span>
              </Link>
              <ChevronRightIcon />
              <span aria-current="page">{section}</span>
            </nav>
          </div>
          <main id="main" className="main-content">
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
