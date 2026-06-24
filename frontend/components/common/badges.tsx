import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  applicationStatusVariant,
  interviewStatusVariant,
  recommendationMeta,
  requisitionStatusVariant,
  scoreRecommendation,
  stageMeta,
} from "@/lib/labels";
import { titleCase } from "@/lib/utils";
import type {
  ApplicationStatus,
  InterviewStatus,
  Recommendation,
  RequisitionStatus,
} from "@/lib/types";

export function StageBadge({
  status,
  className,
}: {
  status?: ApplicationStatus | string | null;
  className?: string;
}) {
  const meta = stageMeta(status as ApplicationStatus);
  return (
    <Badge variant={applicationStatusVariant(status)} className={cn("gap-1.5", className)}>
      <span className={cn("size-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </Badge>
  );
}

export function InterviewStatusBadge({
  status,
  className,
}: {
  status?: InterviewStatus | string | null;
  className?: string;
}) {
  return (
    <Badge variant={interviewStatusVariant(status)} className={className}>
      {titleCase(status)}
    </Badge>
  );
}

export function RequisitionStatusBadge({
  status,
  className,
}: {
  status?: RequisitionStatus | string | null;
  className?: string;
}) {
  return (
    <Badge variant={requisitionStatusVariant(status)} className={className}>
      {titleCase(status)}
    </Badge>
  );
}

export function RecommendationBadge({
  recommendation,
  className,
}: {
  recommendation?: Recommendation | string | null;
  className?: string;
}) {
  const meta = recommendationMeta(recommendation);
  return (
    <Badge variant={meta.variant} className={className}>
      {meta.label}
    </Badge>
  );
}

/** Match-score → recommendation pill (for candidates without an interview yet). */
export function ScoreBadge({
  score,
  className,
}: {
  score?: number | null;
  className?: string;
}) {
  const meta = scoreRecommendation(score);
  return (
    <Badge variant={meta.variant} className={className}>
      {meta.label}
    </Badge>
  );
}
