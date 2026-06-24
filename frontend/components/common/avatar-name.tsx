import Link from "next/link";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn, initials } from "@/lib/utils";

/** Deterministic pastel hue from a string (stable per name). */
function hueFromString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return Math.abs(hash) % 360;
}

export function InitialsAvatar({
  name,
  size = "default",
  hue,
  className,
}: {
  name?: string | null;
  size?: "sm" | "default" | "lg";
  hue?: number;
  className?: string;
}) {
  const h = hue ?? hueFromString(name || "?");
  const sizeClass =
    size === "sm" ? "size-7 text-[10px]" : size === "lg" ? "size-11 text-sm" : "size-9 text-xs";
  return (
    <Avatar className={cn(sizeClass, className)}>
      <AvatarFallback
        style={{
          backgroundColor: `oklch(0.92 0.05 ${h})`,
          color: `oklch(0.42 0.12 ${h})`,
        }}
        className="font-semibold"
      >
        {initials(name)}
      </AvatarFallback>
    </Avatar>
  );
}

export function AvatarName({
  name,
  subtitle,
  href,
  hue,
  size = "default",
  className,
}: {
  name?: string | null;
  subtitle?: string | null;
  href?: string;
  hue?: number;
  size?: "sm" | "default" | "lg";
  className?: string;
}) {
  const body = (
    <div className={cn("flex min-w-0 items-center gap-2.5", className)}>
      <InitialsAvatar name={name} hue={hue} size={size} />
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{name || "—"}</div>
        {subtitle && (
          <div className="text-muted-foreground truncate text-xs">{subtitle}</div>
        )}
      </div>
    </div>
  );
  if (href) {
    return (
      <Link href={href} className="group rounded-md outline-none">
        {body}
      </Link>
    );
  }
  return body;
}
