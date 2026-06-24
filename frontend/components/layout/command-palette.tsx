"use client";

import { useRouter } from "next/navigation";
import { Search, ArrowRight } from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { NAV_SECTIONS } from "@/lib/nav";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();

  const go = (href: string) => {
    onOpenChange(false);
    router.push(href);
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Command menu"
      description="Search pages and run quick actions"
    >
      <CommandInput placeholder="Search pages, candidates, jobs…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Quick actions">
          <CommandItem onSelect={() => go("/candidates")}>
            <Search />
            Search candidates
          </CommandItem>
          <CommandItem onSelect={() => go("/jobs")}>
            <ArrowRight />
            Create a job requisition
          </CommandItem>
          <CommandItem onSelect={() => go("/pipeline")}>
            <ArrowRight />
            Open the ATS pipeline
          </CommandItem>
        </CommandGroup>
        {NAV_SECTIONS.map((section) => (
          <div key={section.title}>
            <CommandSeparator />
            <CommandGroup heading={section.title}>
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <CommandItem
                    key={item.href}
                    value={`${item.label} ${item.keywords?.join(" ") ?? ""}`}
                    onSelect={() => go(item.href)}
                  >
                    <Icon />
                    {item.label}
                    {item.soon && (
                      <span className="text-muted-foreground ml-auto text-xs">
                        Preview
                      </span>
                    )}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </div>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
