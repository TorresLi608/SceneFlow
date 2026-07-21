import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import type { ProductionSettings, ProjectMode } from "@/types/project";

interface ProductionSettingsFormProps {
  settings: ProductionSettings;
  disabled?: boolean;
  onSave: (settings: ProductionSettings) => void;
}

const dimensionsByRatio = {
  "9:16": { width: 1080, height: 1920 },
  "16:9": { width: 1920, height: 1080 },
  "1:1": { width: 1080, height: 1080 },
} as const;

export function ProductionSettingsForm({
  settings,
  disabled = false,
  onSave,
}: ProductionSettingsFormProps) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(settings);

  const updateAspectRatio = (aspectRatio: ProductionSettings["aspectRatio"]) => {
    setDraft((current) => ({
      ...current,
      aspectRatio,
      ...dimensionsByRatio[aspectRatio],
    }));
  };

  return (
    <div className="space-y-3 rounded-lg border border-border/80 bg-muted/20 p-3">
      <div>
        <p className="text-sm font-medium">{t("home.productionSettings")}</p>
        <p className="text-xs text-muted-foreground">{t("home.productionSettingsHint")}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>{t("home.productionMode")}</Label>
          <Select
            value={draft.mode}
            onValueChange={(value) =>
              setDraft((current) => ({ ...current, mode: value as ProjectMode }))
            }
            disabled={disabled}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="comic">{t("home.comicMode")}</SelectItem>
              <SelectItem value="drama">{t("home.dramaMode")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label>{t("home.aspectRatio")}</Label>
          <Select
            value={draft.aspectRatio}
            onValueChange={(value) =>
              updateAspectRatio(value as ProductionSettings["aspectRatio"])
            }
            disabled={disabled}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="9:16">9:16</SelectItem>
              <SelectItem value="16:9">16:9</SelectItem>
              <SelectItem value="1:1">1:1</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label>{t("home.frameRate")}</Label>
          <Select
            value={String(draft.fps)}
            onValueChange={(value) =>
              setDraft((current) => ({ ...current, fps: Number(value) as 24 | 30 }))
            }
            disabled={disabled}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="24">24 FPS</SelectItem>
              <SelectItem value="30">30 FPS</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="target-duration">{t("home.targetDuration")}</Label>
          <Input
            id="target-duration"
            type="number"
            min={10}
            max={600}
            value={Math.round(draft.targetDurationMs / 1000)}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                targetDurationMs: Number(event.target.value) * 1000,
              }))
            }
            disabled={disabled}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="production-language">{t("home.language")}</Label>
        <Input
          id="production-language"
          value={draft.language}
          onChange={(event) =>
            setDraft((current) => ({ ...current, language: event.target.value }))
          }
          placeholder="zh-CN"
          disabled={disabled}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="style-prompt">{t("home.stylePrompt")}</Label>
        <Textarea
          id="style-prompt"
          value={draft.stylePrompt}
          onChange={(event) =>
            setDraft((current) => ({ ...current, stylePrompt: event.target.value }))
          }
          rows={3}
          disabled={disabled}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="negative-prompt">{t("home.negativePrompt")}</Label>
        <Textarea
          id="negative-prompt"
          value={draft.negativePrompt}
          onChange={(event) =>
            setDraft((current) => ({ ...current, negativePrompt: event.target.value }))
          }
          rows={2}
          disabled={disabled}
        />
      </div>

      <Button
        type="button"
        variant="secondary"
        onClick={() => onSave(draft)}
        disabled={disabled || !draft.language.trim() || draft.targetDurationMs < 10000}
      >
        {t("home.saveProductionSettings")}
      </Button>
    </div>
  );
}
