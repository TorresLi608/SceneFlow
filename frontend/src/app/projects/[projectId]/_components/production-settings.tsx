import { useState } from "react";
import { Save, Settings2 } from "lucide-react";

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
    <div className="space-y-4 rounded-2xl border border-border/70 bg-card/60 p-4 shadow-sm backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-border/50 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Settings2 className="size-4" />
          </div>
          <div>
            <p className="text-xs font-bold text-foreground">{t("home.productionSettings")}</p>
            <p className="text-[10px] text-muted-foreground">{t("home.productionSettingsHint")}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-xs font-medium text-foreground">{t("home.productionMode")}</Label>
          <Select
            items={[
              { value: "comic", label: t("home.comicMode") },
              { value: "drama", label: t("home.dramaMode") },
            ]}
            value={draft.mode}
            onValueChange={(value) =>
              setDraft((current) => ({ ...current, mode: value as ProjectMode }))
            }
            disabled={disabled}
          >
            <SelectTrigger className="h-8 rounded-lg text-xs bg-muted/20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="comic" className="text-xs">{t("home.comicMode")}</SelectItem>
              <SelectItem value="drama" className="text-xs">{t("home.dramaMode")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs font-medium text-foreground">{t("home.aspectRatio")}</Label>
          <Select
            items={[
              { value: "9:16", label: "9:16（竖屏短剧）" },
              { value: "16:9", label: "16:9（横屏漫剧）" },
              { value: "1:1", label: "1:1（方形画幅）" },
            ]}
            value={draft.aspectRatio}
            onValueChange={(value) =>
              updateAspectRatio(value as ProductionSettings["aspectRatio"])
            }
            disabled={disabled}
          >
            <SelectTrigger className="h-8 rounded-lg text-xs bg-muted/20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="9:16" className="text-xs">9:16（竖屏短剧）</SelectItem>
              <SelectItem value="16:9" className="text-xs">16:9（横屏漫剧）</SelectItem>
              <SelectItem value="1:1" className="text-xs">1:1（方形画幅）</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs font-medium text-foreground">{t("home.frameRate")}</Label>
          <Select
            items={[
              { value: "24", label: "24 FPS（电影质感）" },
              { value: "30", label: "30 FPS（流畅画质）" },
            ]}
            value={String(draft.fps)}
            onValueChange={(value) =>
              setDraft((current) => ({ ...current, fps: Number(value) as 24 | 30 }))
            }
            disabled={disabled}
          >
            <SelectTrigger className="h-8 rounded-lg text-xs bg-muted/20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="24" className="text-xs">24 FPS（电影质感）</SelectItem>
              <SelectItem value="30" className="text-xs">30 FPS（流畅画质）</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="target-duration" className="text-xs font-medium text-foreground">{t("home.targetDuration")}</Label>
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
            className="h-8 rounded-lg text-xs bg-muted/20"
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="production-language" className="text-xs font-medium text-foreground">{t("home.language")}</Label>
        <Input
          id="production-language"
          value={draft.language}
          onChange={(event) =>
            setDraft((current) => ({ ...current, language: event.target.value }))
          }
          placeholder="zh-CN"
          disabled={disabled}
          className="h-8 rounded-lg text-xs bg-muted/20"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="style-prompt" className="text-xs font-medium text-foreground">{t("home.stylePrompt")}</Label>
        <Textarea
          id="style-prompt"
          value={draft.stylePrompt}
          onChange={(event) =>
            setDraft((current) => ({ ...current, stylePrompt: event.target.value }))
          }
          rows={2}
          disabled={disabled}
          placeholder="例如：Cinematic, anime style, 8k resolution, Unreal Engine 5 render..."
          className="resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="negative-prompt" className="text-xs font-medium text-foreground">{t("home.negativePrompt")}</Label>
        <Textarea
          id="negative-prompt"
          value={draft.negativePrompt}
          onChange={(event) =>
            setDraft((current) => ({ ...current, negativePrompt: event.target.value }))
          }
          rows={2}
          disabled={disabled}
          placeholder="例如：low quality, blurry, distorted limbs, bad anatomy..."
          className="resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background"
        />
      </div>

      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={() => onSave(draft)}
        disabled={disabled || !draft.language.trim() || draft.targetDurationMs < 10000}
        className="w-full h-8 rounded-lg text-xs font-medium cursor-pointer gap-1.5 shadow-xs"
      >
        <Save className="size-3.5" />
        {t("home.saveProductionSettings")}
      </Button>
    </div>
  );
}
