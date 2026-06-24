// Realistic mock data for preview surfaces whose backend isn't built yet
// (Talent Pool / Sourcing, Outreach Campaigns, Offer Management) and the
// AI Assistant. Clearly isolated here so it can be swapped for real endpoints.

export interface SourcedCandidate {
  id: string;
  name: string;
  title: string;
  company: string;
  location: string;
  source: "LinkedIn" | "GitHub" | "Referral" | "Job Board" | "Internal DB";
  matchScore: number; // 0-100
  outreach: "Not contacted" | "Contacted" | "Responded" | "In pipeline";
  skills: string[];
  avatarHue: number;
}

export const SOURCED_CANDIDATES: SourcedCandidate[] = [
  { id: "s1", name: "Priya Sharma", title: "Senior Backend Engineer", company: "Razorpay", location: "Bengaluru", source: "LinkedIn", matchScore: 92, outreach: "Responded", skills: ["Java", "Spring", "Kafka", "AWS"], avatarHue: 262 },
  { id: "s2", name: "Daniel Okoro", title: "Staff SRE", company: "Cloudflare", location: "Remote", source: "GitHub", matchScore: 88, outreach: "Contacted", skills: ["Go", "Kubernetes", "Terraform"], avatarHue: 152 },
  { id: "s3", name: "Mei Lin", title: "ML Engineer", company: "Stripe", location: "Singapore", source: "Referral", matchScore: 85, outreach: "In pipeline", skills: ["Python", "PyTorch", "MLOps"], avatarHue: 320 },
  { id: "s4", name: "Arjun Nair", title: "Frontend Lead", company: "Swiggy", location: "Bengaluru", source: "LinkedIn", matchScore: 81, outreach: "Not contacted", skills: ["React", "TypeScript", "Next.js"], avatarHue: 28 },
  { id: "s5", name: "Sofia Rossi", title: "Product Designer", company: "Figma", location: "Remote", source: "Job Board", matchScore: 79, outreach: "Not contacted", skills: ["Figma", "Design Systems", "Prototyping"], avatarHue: 200 },
  { id: "s6", name: "Kenji Tanaka", title: "Data Platform Engineer", company: "Rakuten", location: "Tokyo", source: "Internal DB", matchScore: 76, outreach: "Contacted", skills: ["Scala", "Spark", "Snowflake"], avatarHue: 96 },
];

export interface OutreachCampaign {
  id: string;
  name: string;
  channel: "Email" | "LinkedIn" | "Multi-channel";
  status: "Active" | "Paused" | "Draft" | "Completed";
  sent: number;
  openRate: number; // %
  replyRate: number; // %
  conversionRate: number; // %
  role: string;
  updated: string;
}

export const OUTREACH_CAMPAIGNS: OutreachCampaign[] = [
  { id: "c1", name: "Senior Backend — Q3 Push", channel: "Multi-channel", status: "Active", sent: 248, openRate: 64, replyRate: 21, conversionRate: 8, role: "Senior Backend Engineer", updated: "2h ago" },
  { id: "c2", name: "SRE Passive Talent", channel: "LinkedIn", status: "Active", sent: 132, openRate: 71, replyRate: 28, conversionRate: 11, role: "Staff SRE", updated: "1d ago" },
  { id: "c3", name: "Design Re-engagement", channel: "Email", status: "Paused", sent: 96, openRate: 52, replyRate: 14, conversionRate: 5, role: "Product Designer", updated: "3d ago" },
  { id: "c4", name: "Referral Nudge — Eng", channel: "Email", status: "Completed", sent: 410, openRate: 58, replyRate: 19, conversionRate: 9, role: "Multiple", updated: "1w ago" },
  { id: "c5", name: "ML Engineer Sourcing", channel: "Multi-channel", status: "Draft", sent: 0, openRate: 0, replyRate: 0, conversionRate: 0, role: "ML Engineer", updated: "just now" },
];

export interface OfferRecord {
  id: string;
  candidate: string;
  role: string;
  status: "Draft" | "Pending Approval" | "Sent" | "Accepted" | "Declined" | "Negotiating";
  ctc: string;
  sentOn: string | null;
  approver: string;
  avatarHue: number;
}

export const OFFERS: OfferRecord[] = [
  { id: "o1", candidate: "Rahul Mehta", role: "Senior Backend Engineer", status: "Pending Approval", ctc: "₹42 LPA", sentOn: null, approver: "D. Manager", avatarHue: 262 },
  { id: "o2", candidate: "Ananya Gupta", role: "Frontend Lead", status: "Sent", ctc: "₹38 LPA", sentOn: "2 days ago", approver: "Approved", avatarHue: 320 },
  { id: "o3", candidate: "Wei Chen", role: "Staff SRE", status: "Negotiating", ctc: "₹55 LPA", sentOn: "5 days ago", approver: "Approved", avatarHue: 152 },
  { id: "o4", candidate: "Fatima Khan", role: "ML Engineer", status: "Accepted", ctc: "₹48 LPA", sentOn: "1 week ago", approver: "Approved", avatarHue: 28 },
  { id: "o5", candidate: "James Carter", role: "Product Designer", status: "Declined", ctc: "₹32 LPA", sentOn: "2 weeks ago", approver: "Approved", avatarHue: 200 },
];

export interface AssistantSuggestion {
  label: string;
  prompt: string;
  href?: string;
}

export const ASSISTANT_SUGGESTIONS: AssistantSuggestion[] = [
  { label: "Find top candidates", prompt: "Show me the highest-matching candidates this week", href: "/candidates" },
  { label: "Draft a job description", prompt: "Generate a JD for a Senior Backend Engineer", href: "/jobs" },
  { label: "Summarize pipeline health", prompt: "Where are candidates getting stuck?", href: "/analytics" },
  { label: "Who needs interview feedback?", prompt: "List interviews awaiting feedback", href: "/evaluations" },
];

export interface AssistantCapability {
  title: string;
  description: string;
}

export const ASSISTANT_CAPABILITIES: AssistantCapability[] = [
  { title: "Search candidates", description: "Natural-language search across the talent pool" },
  { title: "Generate job descriptions", description: "Draft and refine requisitions in seconds" },
  { title: "Summarize resumes", description: "Instant AI summaries and skill extraction" },
  { title: "Schedule interviews", description: "Find slots and book rounds conversationally" },
  { title: "Write outreach", description: "Personalized candidate emails on brand" },
  { title: "Analyze trends", description: "Ask about funnel, sources, and time-to-hire" },
];
