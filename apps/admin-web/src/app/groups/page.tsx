"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import { ApiError, createAdminGroup, listAdminGroups } from "@/lib/api";
import {
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
  Textarea,
} from "@dijione/design-system";

const GROUP_TYPES = ["TEAM", "CLIENT", "SYSTEM"];

function CreateGroupModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [key, setKey] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [groupType, setGroupType] = useState(GROUP_TYPES[0]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createAdminGroup({ key, display_name: displayName, description, group_type: groupType }),
    onSuccess: () => {
      setKey("");
      setDisplayName("");
      setDescription("");
      setGroupType(GROUP_TYPES[0]);
      setError(null);
      onCreated();
      onClose();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not create this group."),
  });

  return (
    <Modal open={open} onClose={onClose} title="Create Group">
      <div className="flex flex-col gap-4">
        <FormField label="Key" htmlFor="group-key" required hint="Unique, machine-readable identifier (e.g. ta-team).">
          <Input id="group-key" value={key} onChange={(e) => setKey(e.target.value)} placeholder="ta-team" />
        </FormField>
        <FormField label="Display Name" htmlFor="group-name" required>
          <Input id="group-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="TA Team" />
        </FormField>
        <FormField label="Description" htmlFor="group-desc">
          <Textarea id="group-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
        </FormField>
        <FormField label="Group Type" htmlFor="group-type">
          <Select id="group-type" value={groupType} onChange={(e) => setGroupType(e.target.value)}>
            {GROUP_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </FormField>
        {error && <p className="text-sm text-dt-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!key.trim() || !displayName.trim()}
          >
            Create Group
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function AdminGroupsPage() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "groups"], queryFn: listAdminGroups });
  const [createOpen, setCreateOpen] = useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "groups"] });

  return (
    <div>
      <PageHeader
        title="Groups"
        description="Access groups let you assign application access to a team once, then add or remove members — everyone in the group inherits the group's module roles in addition to any direct assignments."
        action={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" /> Create Group
          </Button>
        }
      />
      {query.isLoading && <LoadingState label="Loading groups…" />}
      {query.isError && <ErrorState message="Could not load groups." onRetry={() => query.refetch()} />}
      {query.data && query.data.length === 0 && (
        <EmptyState
          title="No access groups yet"
          description="Create a group to assign module access to a whole team at once."
          action={<Button onClick={() => setCreateOpen(true)}>Create Group</Button>}
        />
      )}
      {query.data && query.data.length > 0 && (
        <Table>
          <Thead>
            <tr>
              <Th>Group</Th>
              <Th>Description</Th>
              <Th>Members</Th>
              <Th>Applications</Th>
              <Th>Status</Th>
              <Th />
            </tr>
          </Thead>
          <tbody>
            {query.data.map((g) => (
              <Tr key={g.id}>
                <Td>
                  <p className="font-medium text-dt-text-primary">{g.display_name}</p>
                  <p className="text-xs text-dt-text-secondary">{g.key} · {g.group_type}</p>
                </Td>
                <Td className="max-w-xs truncate text-sm text-dt-text-secondary">{g.description || "—"}</Td>
                <Td className="text-sm text-dt-text-secondary">{g.member_count}</Td>
                <Td className="text-sm text-dt-text-secondary">{g.module_count}</Td>
                <Td>
                  <StatusBadge status={g.status === "ACTIVE" ? "ACTIVE_CLIENT" : "INACTIVE"} label={g.status === "ACTIVE" ? "Active" : "Inactive"} />
                </Td>
                <Td>
                  <Link href={`/groups/${g.id}`} className="flex items-center gap-1 text-sm font-medium text-dt-burnt-orange">
                    Manage <ChevronRight className="size-3.5" />
                  </Link>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}

      <CreateGroupModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={invalidate} />
    </div>
  );
}
