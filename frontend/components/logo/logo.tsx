import Image from "next/image";

import icon from "@/components/logo/logo-icon.png";
import { cn } from "@/lib/utils";

/** The gradient icon mark only (transparent, works on light + dark). */
export function LogoMark({
  className,
  priority,
}: {
  className?: string;
  priority?: boolean;
}) {
  return (
    <Image
      src={icon}
      alt="Talent OS"
      priority={priority}
      className={cn("object-contain", className)}
    />
  );
}

/**
 * Full brand lockup: gradient icon mark + theme-aware wordmark.
 * Pass `collapsed` to render just the mark, or `tone="onPrimary"` when placed
 * on the indigo brand background (login panel).
 */
export function Logo({
  collapsed,
  className,
  priority,
  tone = "default",
}: {
  collapsed?: boolean;
  className?: string;
  priority?: boolean;
  tone?: "default" | "onPrimary";
}) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark priority={priority} className="size-9 shrink-0" />
      {!collapsed && (
        <span className="leading-tight">
          <span className="block text-sm font-semibold tracking-tight">
            Talent OS
          </span>
          <span
            className={cn(
              "block text-[10px] font-medium tracking-wider uppercase",
              tone === "onPrimary"
                ? "text-primary-foreground/70"
                : "text-muted-foreground",
            )}
          >
            AI Recruitment
          </span>
        </span>
      )}
    </span>
  );
}
