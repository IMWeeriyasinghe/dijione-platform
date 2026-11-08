import { EmptyState, PageHeader } from "@dijione/design-system";

export function FuturePlaceholder({ title, description }: { title: string; description: string }) {
  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title={title} description={description} />
      <EmptyState title="Not available yet" description="This section is planned for a later DijiAtWork release." />
    </div>
  );
}
