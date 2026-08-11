"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, createTalentRequest } from "@/lib/api";
import { ENGAGEMENT_TYPES, SENIORITY_LEVELS } from "@/lib/constants";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardContent } from "@/components/ui/Card";
import { FormField, Input, Select, Textarea } from "@/components/ui/FormField";
import { Button } from "@/components/ui/Button";

export default function NewTalentRequestPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const [designation, setDesignation] = useState("");
  const [description, setDescription] = useState("");
  const [skills, setSkills] = useState("");
  const [seniority, setSeniority] = useState<string>(SENIORITY_LEVELS[2]);
  const [location, setLocation] = useState("");
  const [engagementType, setEngagementType] = useState<(typeof ENGAGEMENT_TYPES)[number]>("FULL_TIME");
  const [targetStartDate, setTargetStartDate] = useState("");
  const [notes, setNotes] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      createTalentRequest({
        designation,
        description,
        required_skills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        seniority,
        location,
        engagement_type: engagementType,
        target_start_date: targetStartDate || null,
        notes,
      }),
    onSuccess: (request) => {
      queryClient.invalidateQueries({ queryKey: ["talent-requests"] });
      queryClient.invalidateQueries({ queryKey: ["client-dashboard"] });
      router.push(`/talent-flow/requests/${request.id}`);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not submit the request. Please try again.");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="New Talent Request"
        description="Tell us what you need. Customer Success will review before Talent Acquisition begins sourcing."
      />

      <Card>
        <CardContent className="pt-5">
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <FormField label="Designation" htmlFor="designation" required>
              <Input
                id="designation"
                required
                value={designation}
                onChange={(e) => setDesignation(e.target.value)}
                placeholder="e.g. Senior Power Platform Developer"
              />
            </FormField>

            <FormField label="Description" htmlFor="description" required>
              <Textarea
                id="description"
                required
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What will this person own? What does success look like?"
              />
            </FormField>

            <FormField label="Required Skills" htmlFor="skills" hint="Comma-separated" required>
              <Input
                id="skills"
                required
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
                placeholder="e.g. Power Apps, Dataverse, Azure"
              />
            </FormField>

            <div className="grid gap-5 sm:grid-cols-2">
              <FormField label="Seniority" htmlFor="seniority">
                <Select id="seniority" value={seniority} onChange={(e) => setSeniority(e.target.value)}>
                  {SENIORITY_LEVELS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              </FormField>

              <FormField label="Engagement Type" htmlFor="engagement">
                <Select
                  id="engagement"
                  value={engagementType}
                  onChange={(e) => setEngagementType(e.target.value as (typeof ENGAGEMENT_TYPES)[number])}
                >
                  {ENGAGEMENT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t.replace("_", " ")}
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <FormField label="Location" htmlFor="location">
                <Input
                  id="location"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="e.g. Colombo, Sri Lanka (Hybrid)"
                />
              </FormField>
              <FormField label="Target Start Date" htmlFor="start-date">
                <Input
                  id="start-date"
                  type="date"
                  value={targetStartDate}
                  onChange={(e) => setTargetStartDate(e.target.value)}
                />
              </FormField>
            </div>

            <FormField label="Additional Notes" htmlFor="notes">
              <Textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Anything else Customer Success or Talent Acquisition should know?"
              />
            </FormField>

            {error && <p className="text-sm text-dt-danger">{error}</p>}

            <div className="flex items-center justify-end gap-3 pt-2">
              <Button type="button" variant="secondary" onClick={() => router.back()}>
                Cancel
              </Button>
              <Button type="submit" loading={mutation.isPending}>
                Submit Request
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
