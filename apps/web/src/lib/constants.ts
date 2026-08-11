// Mirrors apps/api/app/core/constants.py — kept in sync by hand for the MVP.

export const CANONICAL_STAGES = [
  "REQUEST_SUBMITTED",
  "REQUIREMENT_CONFIRMED",
  "SOURCING",
  "SCREENING",
  "CLIENT_REVIEW",
  "INTERVIEWS",
  "OFFER",
  "ONBOARDING",
  "DEPLOYED",
] as const;

export const LIFECYCLE_STATUSES = [
  "PENDING_REVIEW",
  "APPROVED",
  "IN_PROGRESS",
  "ON_HOLD",
  "FULFILLED",
  "CANCELLED",
  "REJECTED",
] as const;

export const CUSTOMER_SUCCESS_STATUSES = [
  "PENDING_REVIEW",
  "CLARIFICATION_REQUIRED",
  "REJECTED",
  "APPROVED",
] as const;

export const TA_STATUSES = [
  "NOT_STARTED",
  "VALIDATING",
  "ATS_LINKED",
  "IN_PROGRESS",
  "ON_HOLD",
  "COMPLETED",
] as const;

export const APPLICATION_STATUSES = [
  "ACTIVE",
  "SHORTLISTED",
  "CLIENT_REVIEW",
  "OFFER",
  "HIRED",
  "REJECTED",
  "WITHDRAWN",
] as const;

export const INTERVIEW_STATUSES = [
  "SCHEDULED",
  "COMPLETED",
  "CANCELLED",
  "RESCHEDULED",
  "NO_SHOW",
] as const;

export const INTERVIEW_TYPES = ["INTERNAL_SCREEN", "CLIENT_INTERVIEW", "TECHNICAL", "FINAL"] as const;

export const ENGAGEMENT_TYPES = ["FULL_TIME", "CONTRACT", "PART_TIME", "STAFF_AUGMENTATION"] as const;

export const SENIORITY_LEVELS = ["Junior", "Mid", "Senior", "Lead", "Manager", "Principal"] as const;
