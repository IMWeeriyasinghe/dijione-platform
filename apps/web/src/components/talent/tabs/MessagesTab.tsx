"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Send } from "lucide-react";
import { useState } from "react";
import { listMessages, sendMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn, formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/FormField";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Avatar } from "@/components/ui/Avatar";

export function MessagesTab({ requestId }: { requestId: number }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["messages", requestId],
    queryFn: () => listMessages(requestId),
  });

  const mutation = useMutation({
    mutationFn: () => sendMessage(requestId, body),
    onSuccess: () => {
      setBody("");
      queryClient.invalidateQueries({ queryKey: ["messages", requestId] });
    },
  });

  if (isLoading) return <LoadingState label="Loading messages…" />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className="flex flex-col gap-4">
      {!data || data.length === 0 ? (
        <EmptyState icon={MessageSquare} title="No messages yet" description="Start the conversation below." />
      ) : (
        <div className="flex flex-col gap-3">
          {data.map((m) => {
            const isMine = m.sender_id === user?.id;
            return (
              <div key={m.id} className={cn("flex items-end gap-2.5", isMine && "flex-row-reverse")}>
                <Avatar name={m.sender_name} size={28} />
                <div
                  className={cn(
                    "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm",
                    isMine ? "bg-dt-orange text-white" : "bg-dt-surface-warm text-dt-text-primary"
                  )}
                >
                  <p className={cn("mb-0.5 text-xs font-medium", isMine ? "text-white/80" : "text-dt-text-secondary")}>
                    {m.sender_name}
                  </p>
                  <p className="whitespace-pre-line">{m.body}</p>
                  <p className={cn("mt-1 text-[11px]", isMine ? "text-white/70" : "text-dt-text-secondary/70")}>
                    {formatDateTime(m.created_at)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (body.trim()) mutation.mutate();
        }}
        className="flex items-end gap-3 border-t border-dt-border pt-4"
      >
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Write a message…"
          className="min-h-16"
        />
        <Button type="submit" loading={mutation.isPending} disabled={!body.trim()}>
          <Send className="size-4" />
          Send
        </Button>
      </form>
    </div>
  );
}
