// Test-only prop types for the local mocks of @dijione/design-system and
// next/link. Type-only: nothing here is imported by application code.
import type { ComponentProps, MouseEventHandler, ReactNode } from "react";

export type MockButtonProps = ComponentProps<"button"> & { loading?: boolean };
export type MockInputProps = ComponentProps<"input">;
export type MockTextareaProps = ComponentProps<"textarea">;
export type MockSelectProps = ComponentProps<"select">;
export type MockTdProps = ComponentProps<"td">;
export type MockTrProps = ComponentProps<"tr">;
export type MockThProps = { children?: ReactNode };
export type MockHeadingProps = { title?: ReactNode; description?: ReactNode; action?: ReactNode };
export type MockStatusProps = { label?: ReactNode; status?: ReactNode };
export type MockMetricProps = { label?: ReactNode; value?: ReactNode };
export type MockSortableThProps = { label?: ReactNode };
export type MockFieldProps = { label?: ReactNode; children?: ReactNode };
export type MockErrorProps = { onRetry?: () => void };
export type MockModalProps = { open?: boolean; title?: string; children?: ReactNode };
export type MockLinkProps = {
  href: string;
  children?: ReactNode;
  onClick?: MouseEventHandler<HTMLAnchorElement>;
};
