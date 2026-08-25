"use client";

import { AtSign, Check } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import type { GenerationReferenceInput } from "@/types/project";

import type { ReferenceAssetOption } from "./reference-picker";

const keyOf = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;

export function MentionTextarea({
  id,
  value,
  onChange,
  references,
  onReferencesChange,
  assets,
  limits,
  ...props
}: Omit<React.ComponentProps<typeof Textarea>, "value" | "onChange"> & {
  value: string;
  onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  references: GenerationReferenceInput[];
  onReferencesChange: (next: GenerationReferenceInput[]) => void;
  assets: ReferenceAssetOption[];
  limits: Partial<Record<ReferenceAssetOption["media"], number>>;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);
  const selected = new Set(references.map(keyOf));

  const mention = (asset: ReferenceAssetOption) => {
    const input = inputRef.current;
    const start = input?.selectionStart ?? value.length;
    const end = input?.selectionEnd ?? value.length;
    onChange({ target: { value: `${value.slice(0, start)}@${asset.label} ${value.slice(end)}` } } as React.ChangeEvent<HTMLTextAreaElement>);
    onReferencesChange([...references, { kind: asset.kind, id: asset.id }]);
    setOpen(false);
    requestAnimationFrame(() => input?.focus());
  };

  const available = assets.filter((asset) => {
    if (selected.has(keyOf(asset))) return true;
    const used = assets.filter((item) => item.media === asset.media && selected.has(keyOf(item))).length;
    return used < (limits[asset.media] ?? 0);
  });

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-start gap-2">
        <Textarea
          {...props}
          id={id}
          ref={inputRef}
          value={value}
          onChange={(event) => {
            onChange(event);
            if (event.target.value.endsWith("@")) setOpen(true);
          }}
        />
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger render={<Button type="button" variant="outline" size="icon" aria-label="@" />}>
            <AtSign className="size-4" />
          </PopoverTrigger>
          <PopoverContent align="end" className="max-h-64 overflow-y-auto p-1">
            {available.length ? available.map((asset) => {
              const active = selected.has(keyOf(asset));
              return (
                <button
                  key={keyOf(asset)}
                  type="button"
                  className={cn("flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent", active && "bg-accent")}
                  onClick={() => (active ? onReferencesChange(references.filter((item) => keyOf(item) !== keyOf(asset))) : mention(asset))}
                >
                  {active ? <Check className="size-3.5" /> : <AtSign className="size-3.5 text-muted-foreground" />}
                  <span className="truncate">{asset.label}</span>
                </button>
              );
            }) : <p className="px-2 py-1.5 text-xs text-muted-foreground">{t("episode.mentionEmpty")}</p>}
          </PopoverContent>
        </Popover>
      </div>
      {references.length ? (
        <div className="flex flex-wrap gap-1">
          {references.map((reference) => {
            const asset = assets.find((item) => keyOf(item) === keyOf(reference));
            return asset ? (
              <button
                key={keyOf(reference)}
                type="button"
                className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary hover:bg-destructive/10 hover:text-destructive"
                onClick={() => onReferencesChange(references.filter((item) => keyOf(item) !== keyOf(reference)))}
              >
                @{asset.label} ×
              </button>
            ) : null;
          })}
        </div>
      ) : null}
    </div>
  );
}
