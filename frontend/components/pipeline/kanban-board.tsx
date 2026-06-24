"use client";

import { useState } from "react";
import Link from "next/link";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { ExternalLink, GripVertical, Sparkles } from "lucide-react";

import type { ApplicationBoardItem, ApplicationStatus } from "@/lib/types";
import { PIPELINE_STAGES, scoreRecommendation, type StageMeta } from "@/lib/labels";
import { cn, scoreToPercent } from "@/lib/utils";
import { ScoreRing } from "@/components/common/score";
import { InterviewStatusBadge } from "@/components/common/badges";
import { InitialsAvatar } from "@/components/common/avatar-name";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const COLUMNS = PIPELINE_STAGES.filter((s) => s.key !== "WITHDRAWN");

export function KanbanBoard({
  items,
  onMove,
}: {
  items: ApplicationBoardItem[];
  onMove: (id: string, toStatus: ApplicationStatus) => void;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  const byStatus = (status: string) => items.filter((i) => i.status === status);
  const activeItem = items.find((i) => i.id === activeId) ?? null;

  const onDragStart = (e: DragStartEvent) => setActiveId(String(e.active.id));
  const onDragEnd = (e: DragEndEvent) => {
    setActiveId(null);
    const { active, over } = e;
    if (!over) return;
    const toStatus = String(over.id) as ApplicationStatus;
    const item = items.find((i) => i.id === active.id);
    if (item && item.status !== toStatus) onMove(item.id, toStatus);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setActiveId(null)}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {COLUMNS.map((stage) => (
          <Column key={stage.key} stage={stage} items={byStatus(stage.key)} activeId={activeId} />
        ))}
      </div>
      <DragOverlay>
        {activeItem ? <Card item={activeItem} overlay /> : null}
      </DragOverlay>
    </DndContext>
  );
}

function Column({
  stage,
  items,
  activeId,
}: {
  stage: StageMeta;
  items: ApplicationBoardItem[];
  activeId: string | null;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.key });
  return (
    <div className="flex w-[300px] shrink-0 flex-col">
      <div className="mb-2 flex items-center gap-2 px-1">
        <span className={cn("size-2 rounded-full", stage.dot)} />
        <span className="text-sm font-semibold">{stage.label}</span>
        <Badge variant="muted" className="ml-auto tabular-nums">{items.length}</Badge>
      </div>
      <div
        ref={setNodeRef}
        className={cn(
          "bg-muted/40 flex min-h-[200px] flex-1 flex-col gap-2 rounded-xl border border-dashed p-2 transition-colors",
          isOver && "border-primary/50 bg-primary/5",
        )}
      >
        {items.map((item) => (
          <DraggableCard key={item.id} item={item} dimmed={activeId === item.id} />
        ))}
        {items.length === 0 && (
          <div className="text-muted-foreground flex flex-1 items-center justify-center py-6 text-xs">
            Drop here
          </div>
        )}
      </div>
    </div>
  );
}

function DraggableCard({ item, dimmed }: { item: ApplicationBoardItem; dimmed: boolean }) {
  const { attributes, listeners, setNodeRef } = useDraggable({ id: item.id });
  return (
    <div ref={setNodeRef} className={cn(dimmed && "opacity-40")}>
      <Card item={item} dragHandleProps={{ ...attributes, ...listeners }} />
    </div>
  );
}

function Card({
  item,
  dragHandleProps,
  overlay,
}: {
  item: ApplicationBoardItem;
  dragHandleProps?: Record<string, unknown>;
  overlay?: boolean;
}) {
  const rec = scoreRecommendation(item.match_score);
  return (
    <div
      className={cn(
        "bg-card group rounded-xl border p-3 shadow-card",
        overlay ? "rotate-2 shadow-card-lg" : "",
      )}
    >
      <div className="flex items-start gap-2">
        <button
          {...dragHandleProps}
          className="text-muted-foreground/50 hover:text-muted-foreground -ml-1 cursor-grab touch-none pt-0.5 active:cursor-grabbing"
          aria-label="Drag candidate"
        >
          <GripVertical className="size-4" />
        </button>
        <InitialsAvatar name={item.candidate.full_name} size="sm" />
        <div className="min-w-0 flex-1">
          <Link
            href={`/candidates/${item.candidate.id}`}
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-sm font-medium hover:underline"
          >
            <span className="truncate">{item.candidate.full_name}</span>
            <ExternalLink className="size-3 shrink-0 opacity-0 group-hover:opacity-60" />
          </Link>
          <p className="text-muted-foreground truncate text-xs">
            {item.candidate.current_designation ?? "—"}
          </p>
        </div>
        <ScoreRing score={item.match_score} size={36} strokeWidth={3} />
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Badge variant={rec.variant} className="gap-1">
          <Sparkles className="size-3" /> {rec.label}
        </Badge>
        {item.resume_score != null && (
          <Badge variant="muted">Resume {scoreToPercent(item.resume_score)}</Badge>
        )}
        {item.latest_interview && (
          <InterviewStatusBadge status={item.latest_interview.status} />
        )}
      </div>

      {item.owner && (
        <div className="mt-2.5 flex items-center justify-between border-t pt-2">
          <span className="text-muted-foreground truncate text-xs">{item.requisition.title}</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <InitialsAvatar name={item.owner.name} size="sm" />
              </span>
            </TooltipTrigger>
            <TooltipContent>{item.owner.name}</TooltipContent>
          </Tooltip>
        </div>
      )}
    </div>
  );
}
