<script lang="ts">
  import { browser } from '$app/environment';
  import DOMPurify from 'dompurify';
  import { marked, Renderer } from 'marked';

  let { content }: { content: string } = $props();

  const executionReference =
    /(Execution ID|Çalıştırma kimliği):\s*([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})/gi;
  const renderer = new Renderer();
  renderer.html = ({ text }) =>
    text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

  function renderMarkdown(value: string): string {
    if (!browser) return '';
    const linked = value.replace(
      executionReference,
      (_match, label: string, executionId: string) =>
        `${label}: [${executionId}](/executions/${executionId})`
    );
    const rendered = marked.parse(linked, {
      async: false,
      breaks: true,
      gfm: true,
      renderer
    }) as string;
    return DOMPurify.sanitize(rendered, {
      ALLOWED_TAGS: [
        'a', 'blockquote', 'br', 'code', 'del', 'em', 'h1', 'h2', 'h3',
        'h4', 'h5', 'h6', 'hr', 'li', 'ol', 'p', 'pre', 'strong', 'table',
        'tbody', 'td', 'th', 'thead', 'tr', 'ul'
      ],
      ALLOWED_ATTR: ['href', 'title']
    });
  }
</script>

<div class="markdown-message break-words text-sm leading-5">
  {@html renderMarkdown(content)}
</div>

<style>
  .markdown-message :global(p) {
    margin: 0.3rem 0;
  }

  .markdown-message :global(p:first-child) {
    margin-top: 0;
  }

  .markdown-message :global(p:last-child) {
    margin-bottom: 0;
  }

  .markdown-message :global(strong) {
    font-weight: 600;
  }

  .markdown-message :global(ul),
  .markdown-message :global(ol) {
    margin: 0.35rem 0;
    padding-left: 1.25rem;
  }

  .markdown-message :global(ul) {
    list-style: disc;
  }

  .markdown-message :global(ol) {
    list-style: decimal;
  }

  .markdown-message :global(blockquote) {
    margin: 0.4rem 0;
    border-left: 2px solid var(--border);
    padding-left: 0.75rem;
    color: var(--muted-foreground);
  }

  .markdown-message :global(code) {
    border-radius: 0.3rem;
    background: var(--muted);
    padding: 0.1rem 0.3rem;
    font-family: var(--font-mono);
    font-size: 0.8rem;
  }

  .markdown-message :global(pre) {
    margin: 0.5rem 0;
    max-width: 100%;
    overflow-x: auto;
    border-radius: 0.5rem;
    background: var(--muted);
    padding: 0.75rem;
  }

  .markdown-message :global(pre code) {
    background: transparent;
    padding: 0;
  }

  .markdown-message :global(a) {
    color: var(--primary);
    font-weight: 500;
    text-decoration: underline;
    text-underline-offset: 4px;
  }
</style>
