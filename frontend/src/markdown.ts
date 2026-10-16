import { marked } from "marked";
import DOMPurify from "dompurify";

export function markdown(text: string): string {
  return DOMPurify.sanitize(
    marked.parse(text, { async: false, breaks: true }),
    {
      FORBID_TAGS: ["style", "iframe", "form", "input", "img"],
      FORBID_ATTR: ["style"],
    },
  );
}
