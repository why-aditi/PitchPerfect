"use client";

import { Button, Card, Input } from "@/components/ui";
import { CopyButton, Group, Hint, IconButton, IconPlus, IconTrash, Warn } from "./bits";

/**
 * The origin list is compared against the browser's Origin header on /start-call, so it has
 * to be exactly what a browser sends: scheme, host, optional port, nothing else. A trailing
 * path here is a call that gets refused with no explanation on the host page.
 */
export function originError(raw: string): string | null {
  const value = raw.trim();
  if (!value) return "Empty.";

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return "Include the scheme, like https://example.com";
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return "Only http and https.";
  if (url.username || url.password) return "No credentials in an origin.";
  if (url.search || url.hash || (url.pathname !== "/" && url.pathname !== ""))
    return `An origin is scheme and host only — use ${url.origin}`;
  if (value !== url.origin && value !== `${url.origin}/`) return `Use ${url.origin}`;
  return null;
}

export function EmbedTab({
  id,
  isNew,
  origins,
  onChange,
}: {
  id: string;
  isNew: boolean;
  origins: string[];
  onChange: (next: string[]) => void;
}) {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const snippet = `<script src="${apiBase}/embed.js?agent=${id}" async></script>`;

  const trimmed = origins.map((o) => o.trim()).filter(Boolean);
  const duplicated = trimmed.filter((o, i) => trimmed.indexOf(o) !== i);

  return (
    <div className="space-y-10">
      <Group title="Embed snippet">
        {isNew ? (
          <p className="rounded-xl border border-dashed border-line px-6 py-8 text-center text-sm text-muted">
            The snippet carries the agent id, so it appears once you have created the agent.
          </p>
        ) : (
          <Card className="space-y-3 p-4">
            <pre className="overflow-x-auto rounded-lg border border-line-soft bg-surface p-3 font-mono text-xs leading-relaxed text-ink">
              {snippet}
            </pre>
            <div className="flex items-center justify-between gap-4">
              <Hint>
                Paste it anywhere in the page. It injects a launcher and an iframe carrying
                allow=&quot;microphone&quot;, so the host page has to be on HTTPS for the mic
                prompt to appear.
              </Hint>
              <CopyButton text={snippet} label="Copy snippet" />
            </div>
          </Card>
        )}
      </Group>

      <Group
        title="Allowed origins"
        action={
          <Button
            variant="ghost"
            className="px-3 py-1.5 text-xs"
            onClick={() => onChange([...origins, ""])}
          >
            <IconPlus />
            Add origin
          </Button>
        }
      >
        <Hint>
          A call from an origin that is not on this list is refused before it starts. The list is
          the control that matters on this surface, so an empty list means the embed works
          nowhere — including on your own demo page.
        </Hint>

        {origins.length === 0 && (
          <Warn>
            No origins listed. Every call from the embed will be refused until one is added.
          </Warn>
        )}
        {duplicated.length > 0 && <Warn>{duplicated[0]} is listed twice.</Warn>}

        <div className="space-y-2">
          {origins.map((origin, i) => {
            const error = origin.trim() ? originError(origin) : null;
            return (
              // Index keys: rows are plain strings the operator reorders by editing, not by
              // dragging, so there is no identity to key on.
              <div key={i} className="space-y-1">
                <div className="flex items-center gap-2">
                  <Input
                    value={origin}
                    spellCheck={false}
                    placeholder="https://vantage.example.com"
                    onChange={(e) =>
                      onChange(origins.map((o, n) => (n === i ? e.target.value : o)))
                    }
                    className="font-mono"
                  />
                  <IconButton
                    label="Remove origin"
                    tone="danger"
                    onClick={() => onChange(origins.filter((_, n) => n !== i))}
                  >
                    <IconTrash />
                  </IconButton>
                </div>
                {error && <p className="pl-1 text-xs text-escalate">{error}</p>}
              </div>
            );
          })}
        </div>

        <Hint>
          Localhost counts as its own origin: add http://localhost:3000 while you are developing
          the host page.
        </Hint>
      </Group>
    </div>
  );
}
