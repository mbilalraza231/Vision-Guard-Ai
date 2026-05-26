import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Helpers for timezone-aware date formatting
export function formatDateTime(date: Date | number | string, timezone: string = 'UTC') {
  const d = new Date(date);
  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', second: 'numeric', hour12: true
  }).format(d);
}

export function formatTimeString(date: Date | number | string, timezone: string = 'UTC') {
  const d = new Date(date);
  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
  }).format(d);
}
