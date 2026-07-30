export type ChatMessagePart = {
  text: string;
  executionId?: string;
};

const executionReference =
  /(Execution ID|Çalıştırma kimliği):\s*([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})/gi;

export function linkExecutionReferences(content: string): ChatMessagePart[] {
  const parts: ChatMessagePart[] = [];
  let offset = 0;

  for (const match of content.matchAll(executionReference)) {
    const index = match.index ?? 0;
    if (index > offset) parts.push({ text: content.slice(offset, index) });
    parts.push({ text: `${match[1]}: ` });
    parts.push({ text: match[2], executionId: match[2] });
    offset = index + match[0].length;
  }

  if (offset < content.length) parts.push({ text: content.slice(offset) });
  return parts.length ? parts : [{ text: content }];
}
