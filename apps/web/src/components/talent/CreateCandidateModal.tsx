"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, createCandidate } from "@/lib/api";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { FormField, Input, Textarea } from "@/components/ui/FormField";

export function CreateCandidateModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [title, setTitle] = useState("");
  const [skills, setSkills] = useState("");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createCandidate({
        full_name: fullName,
        email,
        professional_title: title,
        summary,
        skills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        source: "MANUAL",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
      setFullName("");
      setEmail("");
      setTitle("");
      setSkills("");
      setSummary("");
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not add this candidate."),
  });

  return (
    <Modal open={open} onClose={onClose} title="Add Candidate">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
        className="flex flex-col gap-4"
      >
        <FormField label="Full Name" htmlFor="full-name" required>
          <Input id="full-name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </FormField>
        <FormField label="Email" htmlFor="email" required>
          <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </FormField>
        <FormField label="Professional Title" htmlFor="title">
          <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </FormField>
        <FormField label="Skills" htmlFor="skills" hint="Comma-separated">
          <Input id="skills" value={skills} onChange={(e) => setSkills(e.target.value)} />
        </FormField>
        <FormField label="Summary" htmlFor="summary">
          <Textarea id="summary" value={summary} onChange={(e) => setSummary(e.target.value)} />
        </FormField>
        {error && <p className="text-sm text-dt-danger">{error}</p>}
        <div className="flex justify-end gap-3 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Add Candidate
          </Button>
        </div>
      </form>
    </Modal>
  );
}
