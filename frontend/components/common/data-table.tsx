"use client";

import type { ReactNode } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { EmptyState, TableSkeleton } from "./states";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  headClassName?: string;
}

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  onRowClick,
  loading,
  empty,
  className,
  skeletonRows = 8,
}: {
  columns: Column<T>[];
  rows: T[];
  getRowId: (row: T, index: number) => string;
  onRowClick?: (row: T) => void;
  loading?: boolean;
  empty?: ReactNode;
  className?: string;
  skeletonRows?: number;
}) {
  if (loading) {
    return (
      <div className="rounded-xl border p-4">
        <TableSkeleton rows={skeletonRows} cols={columns.length} />
      </div>
    );
  }

  if (!rows.length) {
    return (
      <>{empty ?? <EmptyState title="Nothing here yet" description="No records match." />}</>
    );
  }

  const alignClass = (a?: Column<T>["align"]) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <div className={cn("bg-card overflow-hidden rounded-xl border shadow-card", className)}>
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            {columns.map((c) => (
              <TableHead
                key={c.key}
                className={cn(alignClass(c.align), c.headClassName)}
              >
                {c.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow
              key={getRowId(row, i)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn(onRowClick && "cursor-pointer")}
            >
              {columns.map((c) => (
                <TableCell key={c.key} className={cn(alignClass(c.align), c.className)}>
                  {c.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
