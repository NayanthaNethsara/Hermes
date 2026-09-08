import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function cleanWikilinks(text: string): string {
  if (!text) return "";
  return text.replace(/\[\[(.*?)\]\]/g, "$1");
}
