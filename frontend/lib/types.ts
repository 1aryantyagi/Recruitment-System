// ===== Enums =====
export type Role = "HR" | "DELIVERY_MANAGER" | "ADMIN";
export type WorkMode = "REMOTE" | "HYBRID" | "ONSITE";
export type SeniorityLevel =
  | "INTERN"
  | "JUNIOR"
  | "MID"
  | "SENIOR"
  | "LEAD"
  | "MANAGER"
  | "DIRECTOR";
export type RequisitionStatus =
  | "DRAFT"
  | "OPEN"
  | "ON_HOLD"
  | "CLOSED"
  | "CANCELLED";
export type ApplicationStatus =
  | "NEW"
  | "SCREENING"
  | "SHORTLISTED"
  | "INTERVIEW_SCHEDULED"
  | "OFFERED"
  | "REJECTED"
  | "WITHDRAWN"
  | "HIRED";
export type RoundType =
  | "L1"
  | "L2"
  | "L3"
  | "HR"
  | "FINAL"
  | "TECHNICAL"
  | "CULTURAL";
export type InterviewStatus =
  | "SCHEDULED"
  | "COMPLETED"
  | "CANCELLED"
  | "NO_SHOW"
  | "RESCHEDULED";
export type Recommendation =
  | "STRONG_YES"
  | "YES"
  | "MAYBE"
  | "NO"
  | "STRONG_NO";

export const WORK_MODES: WorkMode[] = ["REMOTE", "HYBRID", "ONSITE"];
export const SENIORITY_LEVELS: SeniorityLevel[] = [
  "INTERN",
  "JUNIOR",
  "MID",
  "SENIOR",
  "LEAD",
  "MANAGER",
  "DIRECTOR",
];
export const REQUISITION_STATUSES: RequisitionStatus[] = [
  "DRAFT",
  "OPEN",
  "ON_HOLD",
  "CLOSED",
  "CANCELLED",
];
export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "NEW",
  "SCREENING",
  "SHORTLISTED",
  "INTERVIEW_SCHEDULED",
  "OFFERED",
  "REJECTED",
  "WITHDRAWN",
  "HIRED",
];
export const ROUND_TYPES: RoundType[] = [
  "L1",
  "L2",
  "L3",
  "HR",
  "FINAL",
  "TECHNICAL",
  "CULTURAL",
];
export const INTERVIEW_STATUSES: InterviewStatus[] = [
  "SCHEDULED",
  "COMPLETED",
  "CANCELLED",
  "NO_SHOW",
  "RESCHEDULED",
];
export const RECOMMENDATIONS: Recommendation[] = [
  "STRONG_YES",
  "YES",
  "MAYBE",
  "NO",
  "STRONG_NO",
];

// ===== Envelopes =====
export interface ListResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

// ===== Auth / User =====
export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  is_interviewer: boolean;
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// ===== Candidate =====
export interface CandidateListItem {
  id: string;
  full_name: string;
  email: string;
  current_location?: string | null;
  domain?: string | null;
  total_experience_years?: number | null;
  current_company?: string | null;
  current_designation?: string | null;
  notice_period_days?: number | null;
  work_mode_preference?: WorkMode | null;
  source?: string | null;
  ai_summary?: string | null;
  is_blacklisted: boolean;
  created_at: string;
  // present on ranked candidate lists
  match_score?: number | null;
  score_breakdown?: ScoreBreakdown | null;
}

export interface CandidateSkill {
  id: string;
  skill_id: string;
  skill_name: string;
  category?: string | null;
  proficiency_level?: string | null;
  years_of_experience?: number | null;
  is_verified: boolean;
}

export interface CandidateResume {
  id: string;
  is_latest: boolean;
  uploaded_at: string;
  has_file: boolean;
  file_url?: string | null;
}

export interface CandidateScore {
  requisition_id: string;
  requisition_title?: string | null;
  total_score: number;
  skills_score?: number | null;
  experience_score?: number | null;
  skills_depth_score?: number | null;
  location_score?: number | null;
  notice_period_score?: number | null;
  passed_ats?: boolean;
}

export interface ScoreBreakdown {
  skills_score?: number | null;
  experience_score?: number | null;
  skills_depth_score?: number | null;
  location_score?: number | null;
  notice_period_score?: number | null;
  [key: string]: number | null | undefined;
}

export interface CandidateApplication {
  id: string;
  requisition_id: string;
  status: ApplicationStatus;
  match_score?: number | null;
}

export interface CandidateCall {
  id: string;
  requisition_id?: string | null;
  status: string;
  ai_score?: number | null;
  transcript?: string | null;
  screening_answers?: Record<string, unknown> | null;
  question_set?: unknown;
  called_at?: string | null;
}

export interface CandidateInterview {
  id: string;
  requisition_id?: string | null;
  round_type: RoundType;
  round_number?: number | null;
  status: InterviewStatus;
  scheduled_at?: string | null;
  meeting_link?: string | null;
  ai_overall_rating?: number | null;
  ai_analysis?: unknown;
  feedback?: unknown;
}

export interface CandidateDetail extends CandidateListItem {
  phone?: string | null;
  current_ctc?: number | null;
  expected_ctc?: number | null;
  linkedin_url?: string | null;
  portfolio_url?: string | null;
  availability_date?: string | null;
  shift_preference?: string | null;
  source_detail?: string | null;
  custom_metadata?: Record<string, unknown> | null;
  blacklist_note?: string | null;
  skills: CandidateSkill[];
  resumes: CandidateResume[];
  scores: CandidateScore[];
  applications: CandidateApplication[];
  calls: CandidateCall[];
  interviews: CandidateInterview[];
}

export interface UploadResultItem {
  filename: string;
  candidate_id?: string;
  is_new?: boolean;
  ai_summary?: string;
  skills?: string[];
  error?: string;
  message?: string;
}

export interface UploadResponse {
  results: UploadResultItem[];
}

// ===== Requisition =====
export interface RequisitionListItem {
  id: string;
  title: string;
  domain?: string | null;
  department?: string | null;
  seniority_level?: SeniorityLevel | null;
  location?: string | null;
  work_mode?: WorkMode | null;
  min_experience_years?: number | null;
  max_experience_years?: number | null;
  number_of_openings: number;
  status: RequisitionStatus;
  created_at: string;
}

export interface RequisitionSkill {
  skill_id?: string | null;
  skill_name: string;
  is_mandatory: boolean;
  minimum_years?: number | null;
}

export interface RequisitionDetail extends RequisitionListItem {
  description?: string | null;
  skills: RequisitionSkill[];
  pipeline_count?: number | null;
  min_budget_ctc?: number | null;
  max_budget_ctc?: number | null;
}

export interface RequisitionCreateSkill {
  skill_id?: string;
  skill_name?: string;
  is_mandatory: boolean;
  minimum_years?: number;
}

export interface RequisitionCreate {
  title: string;
  description?: string;
  domain_id?: string;
  department_id?: string;
  seniority_level?: SeniorityLevel;
  location?: string;
  work_mode?: WorkMode;
  shift_timing?: string;
  min_experience_years?: number;
  max_experience_years?: number;
  min_budget_ctc?: number;
  max_budget_ctc?: number;
  number_of_openings: number;
  hiring_manager_id?: string;
  target_close_date?: string;
  skills: RequisitionCreateSkill[];
}

// ===== Skills / Meta =====
export interface Skill {
  id: string;
  name: string;
  category: string;
  is_verified: boolean;
}

export interface SkillsResponse {
  by_category: Record<string, Skill[]>;
  count: number;
}

export interface NamedEntity {
  id: string;
  name: string;
}

export interface StatusReason {
  id: string;
  status: string;
  reason: string;
}

export interface Interviewer {
  id: string;
  name: string;
  email: string;
  role: Role;
  is_interviewer: boolean;
}

// ===== Interviews =====
export interface Interview {
  id: string;
  candidate_id?: string;
  requisition_id?: string | null;
  interviewer_id?: string | null;
  round_type: RoundType;
  round_number?: number | null;
  status: InterviewStatus;
  scheduled_at?: string | null;
  meeting_link?: string | null;
  ai_overall_rating?: number | null;
  ai_analysis?: unknown;
  feedback?: InterviewFeedback | null;
}

export interface InterviewFeedback {
  human_summary?: string | null;
  human_strengths?: string | null;
  human_concerns?: string | null;
  technical_rating?: number | null;
  communication_rating?: number | null;
  problem_solving_rating?: number | null;
  culture_fit_rating?: number | null;
  overall_rating?: number | null;
  recommendation?: Recommendation | null;
  is_submitted?: boolean;
}

export interface FeedbackResponse {
  interview: Interview;
  ai_analysis?: unknown;
  ai_overall_rating?: number | null;
  feedback?: InterviewFeedback | null;
}

// ===== Analytics =====
export interface FunnelStage {
  stage: string;
  count: number;
  conversion_rate?: number | null;
}

export interface SourceStat {
  source: string;
  candidates: number;
  avg_match_score?: number | null;
  hired: number;
  hire_rate?: number | null;
}

export interface OpenReqStat {
  id: string;
  title: string;
  days_open: number;
  openings: number;
  pipeline_count: number;
}

export interface DashboardAnalytics {
  totals: {
    candidates: number;
    open_requisitions: number;
    applications: number;
    screening_calls: number;
    interviews: number;
    feedback_submitted: number;
  };
  funnel: FunnelStage[];
  hire_rate?: number | null;
  sources: SourceStat[];
  open_requisitions: OpenReqStat[];
  time_to_hire: {
    overall_avg_days?: number | null;
    hired_count?: number | null;
  };
}
