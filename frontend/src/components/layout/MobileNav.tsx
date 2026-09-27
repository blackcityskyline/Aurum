import { NavLink } from "react-router-dom";
import { LayoutDashboard, ArrowLeftRight, MessageSquare, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

const MOBILE_NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, labelKey: "nav.dashboard" as const },
  { to: "/transactions", icon: ArrowLeftRight, labelKey: "nav.transactions" as const },
  { to: "/chat", icon: MessageSquare, labelKey: "nav.chat" as const },
  { to: "/settings", icon: Settings, labelKey: "nav.settings" as const },
];

export function MobileNav() {
  const { t } = useTranslation();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-surface-0 pb-[env(safe-area-inset-bottom)] md:hidden">
      <div className="flex items-center justify-around">
        {MOBILE_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs transition-colors",
                  isActive ? "text-primary" : "text-text-muted hover:text-text-secondary"
                )
              }
            >
              <Icon size={20} />
              <span className="truncate text-[10px]">{t(item.labelKey)}</span>
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
