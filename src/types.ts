export type Role = "developer" | "admin";
export type PageKey =
  | "home"
  | "dashboard"
  | "requests"
  | "file-placement"
  | "monitoring"
  | "ms-portal"
  | "admin";

export interface NavItem {
  key: PageKey;
  label: string;
  adminOnly?: boolean;
  href?: string;
}
