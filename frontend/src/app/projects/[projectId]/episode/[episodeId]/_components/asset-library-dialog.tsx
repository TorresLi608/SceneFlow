"use client";

import {
  Check,
  Film,
  FolderOpen,
  ImageIcon,
  Library,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Upload,
  Volume2,
  X,
  Layers,
} from "lucide-react";
import Image from "next/image";
import { useMemo, useState } from "react";

import {
  createAssetAction,
  deleteAssetAction,
  mergeAssetsAction,
  updateAssetAction,
} from "@/actions/projects-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Asset } from "@/types/project";
import { MediaPreviewDialog } from "./media-preview-dialog";

const toDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

export function AssetLibraryDialog({
  projectId,
  open,
  onOpenChange,
  assets,
  generatedImages = [],
  onChanged,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  assets: Asset[];
  generatedImages?: { id: string; name: string; url: string }[];
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Asset["kind"]>("image");
  const [editing, setEditing] = useState<Asset | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [data, setData] = useState("");
  const [fileName, setFileName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ kind: "image" | "video"; url: string; title: string } | null>(null);

  const visible = assets.filter((asset) => asset.kind === tab);
  const counts = {
    image: assets.filter((a) => a.kind === "image").length,
    video: assets.filter((a) => a.kind === "video").length,
    audio: assets.filter((a) => a.kind === "audio").length,
  };

  const mergeOptions = useMemo(
    () => [
      ...assets.filter((asset) => asset.kind === "image"),
      ...generatedImages.map((image) => ({
        id: image.id,
        name: image.name,
        url: image.url,
        kind: "image" as const,
      })),
    ],
    [assets, generatedImages]
  );

  const reset = () => {
    setEditing(null);
    setName("");
    setDescription("");
    setData("");
    setFileName("");
    setError(null);
  };

  const startEdit = (asset: Asset) => {
    setEditing(asset);
    setName(asset.name);
    setDescription(asset.description);
    setData(asset.url ?? "");
    setFileName("");
    setError(null);
  };

  const submit = async () => {
    if (!name.trim() || (!editing && !data.trim())) return;
    setBusy(true);
    try {
      if (editing) {
        await updateAssetAction(projectId, editing.id, {
          name: name.trim(),
          description,
          ...(data ? { data } : {}),
        });
      } else {
        await createAssetAction(projectId, {
          name: name.trim(),
          description,
          kind: tab,
          data,
        });
      }
      reset();
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const [pendingDelete, setPendingDelete] = useState<Asset | null>(null);
  const [deleting, setDeleting] = useState(false);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteAssetAction(projectId, pendingDelete.id);
      setSelected((ids) => ids.filter((id) => id !== pendingDelete.id));
      if (editing?.id === pendingDelete.id) reset();
      setPendingDelete(null);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setDeleting(false);
    }
  };

  const merge = async () => {
    if (selected.length < 1 || !name.trim()) return;
    setBusy(true);
    try {
      await mergeAssetsAction(projectId, {
        name: name.trim(),
        description,
        kind: "image",
        assetIds: selected,
      });
      reset();
      setSelected([]);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="w-[90vw] max-w-4xl sm:max-w-4xl lg:max-w-5xl max-h-[85vh] flex flex-col p-5 gap-3.5">
          <DialogHeader className="border-b border-border/50 pb-2.5">
            <div className="flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Library className="size-4" />
              </div>
              <div>
                <DialogTitle className="text-base font-semibold">
                  {t("episode.assetLibrary")}
                </DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                  {t("episode.assetLibraryDesc")}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          {/* Category Tabs */}
          <div className="flex items-center justify-between border-b border-border/60 pb-1">
            <div className="flex items-center gap-2">
              {(["image", "video", "audio"] as const).map((kind) => {
                const active = tab === kind;
                const Icon = kind === "image" ? ImageIcon : kind === "video" ? Film : Volume2;
                return (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => {
                      setTab(kind);
                      reset();
                    }}
                    className={cn(
                      "flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all cursor-pointer",
                      active
                        ? "bg-primary/10 text-primary shadow-2xs font-semibold ring-1 ring-primary/30"
                        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                    )}
                  >
                    <Icon className="size-3.5" />
                    <span>{t(`episode.referenceType.${kind}`)}</span>
                    <Badge
                      variant={active ? "default" : "secondary"}
                      className="ml-1 px-1.5 py-0 text-[10px] font-mono h-4"
                    >
                      {counts[kind]}
                    </Badge>
                  </button>
                );
              })}
            </div>

            {editing ? (
              <Button
                size="xs"
                variant="ghost"
                onClick={reset}
                className="text-xs text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <X className="mr-1 size-3" />
                取消编辑
              </Button>
            ) : null}
          </div>

          {/* Body Content Grid */}
          <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[1fr_320px] lg:grid-cols-[1fr_350px] overflow-hidden">
            {/* Left: Asset List Grid */}
            <div className="flex flex-col min-h-0 rounded-xl border border-border/60 bg-muted/10 p-3.5 overflow-hidden">
              <div className="flex items-center justify-between pb-2.5 mb-2 border-b border-border/40 text-xs font-medium text-muted-foreground">
                <span>素材列表 ({visible.length})</span>
                <span className="text-[11px] opacity-70">点击可预览大图</span>
              </div>

              {visible.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center text-muted-foreground">
                  <FolderOpen className="size-10 opacity-30" />
                  <p className="text-xs">{t("episode.assetEmpty")}</p>
                  <p className="text-[11px] opacity-70">在右侧面板添加新素材或上传本地文件</p>
                </div>
              ) : (
                <div className="grid min-h-0 flex-1 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 overflow-y-auto pr-1 content-start auto-rows-max chat-message-list-scrollbar">
                  {visible.map((asset) => (
                    <div
                      key={asset.id}
                      className={cn(
                        "group relative flex flex-col h-fit rounded-xl border bg-card p-2.5 transition-all shadow-2xs hover:shadow-md",
                        editing?.id === asset.id
                          ? "border-primary ring-1 ring-primary/40 bg-primary/[0.03]"
                          : "border-border/70 hover:border-primary/50"
                      )}
                    >
                      {/* Media Thumbnail */}
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => {
                          if (asset.url && (asset.kind === "image" || asset.kind === "video")) {
                            setPreview({
                              kind: asset.kind,
                              url: asset.url,
                              title: asset.name,
                            });
                          }
                        }}
                        className="relative aspect-video w-full overflow-hidden rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center cursor-zoom-in"
                      >
                        {asset.kind === "image" && asset.url ? (
                          <Image
                            src={asset.url}
                            alt=""
                            fill
                            unoptimized
                            sizes="240px"
                            className="object-cover transition-transform duration-300 group-hover:scale-105"
                          />
                        ) : asset.kind === "video" ? (
                          <Film className="size-6 text-muted-foreground opacity-60" />
                        ) : (
                          <Volume2 className="size-6 text-muted-foreground opacity-60" />
                        )}
                        <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-[11px]">
                          点击预览
                        </div>
                      </div>

                      {/* Info & Actions */}
                      <div className="mt-2.5 flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-semibold text-foreground">
                            {asset.name}
                          </p>
                          {asset.description ? (
                            <p className="truncate text-[11px] text-muted-foreground mt-0.5">
                              {asset.description}
                            </p>
                          ) : null}
                        </div>

                        <div className="flex items-center gap-0.5 shrink-0">
                          <Button
                            size="icon-xs"
                            variant="ghost"
                            onClick={() => startEdit(asset)}
                            title="编辑"
                            className="text-muted-foreground hover:text-foreground cursor-pointer"
                          >
                            <Pencil className="size-3.5" />
                          </Button>
                          <Button
                            size="icon-xs"
                            variant="ghost"
                            onClick={() => setPendingDelete(asset)}
                            title="删除"
                            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Right: Add / Edit Form & Merge Panel */}
            <div className="flex flex-col min-h-0 gap-4 overflow-y-auto pr-1 chat-message-list-scrollbar">
              {/* Form Section */}
              <div className="flex flex-col gap-3 rounded-xl border border-border/70 bg-card/60 p-4 shadow-sm">
                <div className="flex items-center justify-between border-b border-border/40 pb-2">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    {editing ? <Pencil className="size-3.5 text-primary" /> : <Plus className="size-3.5 text-primary" />}
                    {editing ? t("episode.assetEdit") : t("episode.assetAdd")}
                  </span>
                  {editing ? (
                    <Badge variant="outline" className="text-[10px] text-primary border-primary/40">
                      编辑中
                    </Badge>
                  ) : null}
                </div>

                {error ? (
                  <p className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-1.5 text-xs text-destructive">
                    {error}
                  </p>
                ) : null}

                <Field>
                  <FieldLabel className="text-xs text-muted-foreground">
                    {t("episode.assetName")} *
                  </FieldLabel>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t("episode.assetName")}
                    className="text-xs h-8 bg-background/80"
                  />
                </Field>

                <Field>
                  <FieldLabel className="text-xs text-muted-foreground">
                    {t("episode.assetDescription")}
                  </FieldLabel>
                  <Textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder={t("episode.assetDescription")}
                    className="min-h-16 text-xs bg-background/80 resize-y"
                  />
                </Field>

                {tab === "image" ? (
                  <Field>
                    <FieldLabel className="text-xs text-muted-foreground">
                      图片资源 (URL 或 本地上传)
                    </FieldLabel>
                    <div className="flex flex-col gap-2">
                      <Input
                        value={data.startsWith("data:") ? "" : data}
                        onChange={(e) => {
                          setData(e.target.value);
                          setFileName("");
                        }}
                        placeholder={fileName ? `已选择: ${fileName}` : t("episode.assetUrl")}
                        className="text-xs h-8 bg-background/80 font-mono"
                      />
                      <label className="flex h-9 w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/80 bg-muted/30 px-3 text-xs font-medium text-muted-foreground hover:border-primary/60 hover:bg-muted/50 hover:text-foreground transition-colors">
                        <Upload className="size-3.5" />
                        <span>{fileName ? `重新选择 (${fileName})` : t("episode.assetUpload")}</span>
                        <input
                          type="file"
                          accept="image/png,image/jpeg,image/webp"
                          className="hidden"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (!file) return;
                            setError(null);
                            setFileName(file.name);
                            if (!name.trim()) {
                              setName(file.name.replace(/\.[^/.]+$/, ""));
                            }
                            void toDataUrl(file)
                              .then(setData)
                              .catch((cause) =>
                                setError(cause instanceof Error ? cause.message : String(cause))
                              );
                            e.currentTarget.value = "";
                          }}
                        />
                      </label>
                    </div>
                  </Field>
                ) : (
                  <Field>
                    <FieldLabel className="text-xs text-muted-foreground">
                      {t("episode.assetUrl")}
                    </FieldLabel>
                    <Input
                      value={data}
                      onChange={(e) => setData(e.target.value)}
                      placeholder={t("episode.assetUrl")}
                      className="text-xs h-8 bg-background/80 font-mono"
                    />
                  </Field>
                )}

                <div className="pt-1 flex gap-2">
                  <Button
                    size="sm"
                    disabled={busy || !name.trim() || (!editing && !data.trim())}
                    onClick={() => void submit()}
                    className="flex-1 cursor-pointer font-medium"
                  >
                    {busy ? (
                      <Loader2 data-icon="inline-start" className="animate-spin" />
                    ) : editing ? (
                      <Check data-icon="inline-start" />
                    ) : (
                      <Plus data-icon="inline-start" />
                    )}
                    {t("episode.assetSave")}
                  </Button>
                  {editing ? (
                    <Button size="sm" variant="outline" onClick={reset} className="cursor-pointer">
                      取消
                    </Button>
                  ) : null}
                </div>
              </div>

              {/* Merge Assets Section (only for image tab) */}
              {tab === "image" && !editing ? (
                <div className="flex flex-col gap-3 rounded-xl border border-border/70 bg-card/60 p-4 shadow-sm">
                  <div className="flex items-center justify-between border-b border-border/40 pb-2">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <Layers className="size-3.5 text-primary" />
                      {t("episode.assetMerge")}
                    </span>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      已选 {selected.length} 张
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    {t("episode.assetMergeHint")}
                  </p>

                  <div className="max-h-40 space-y-1.5 overflow-y-auto rounded-lg border border-border/50 bg-muted/30 p-2 text-xs chat-message-list-scrollbar">
                    {mergeOptions.map((item) => {
                      const checked = selected.includes(item.id);
                      return (
                        <label
                          key={item.id}
                          className={cn(
                            "flex items-center gap-2 rounded-md p-1.5 transition-colors cursor-pointer",
                            checked ? "bg-primary/10 text-primary font-medium" : "hover:bg-muted/60"
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() =>
                              setSelected((ids) =>
                                ids.includes(item.id)
                                  ? ids.filter((id) => id !== item.id)
                                  : [...ids, item.id]
                              )
                            }
                            className="rounded border-border"
                          />
                          <span className="truncate flex-1 text-xs">{item.name}</span>
                        </label>
                      );
                    })}
                  </div>

                  <Field>
                    <FieldLabel className="text-xs text-muted-foreground">合并后素材名称</FieldLabel>
                    <Input
                      value={selected.length ? name : ""}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="如：主要场景组合总图"
                      className="text-xs h-8 bg-background/80"
                    />
                  </Field>

                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy || !selected.length || !name.trim()}
                    onClick={() => void merge()}
                    className="cursor-pointer font-medium"
                  >
                    {busy ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Layers data-icon="inline-start" />}
                    {t("episode.assetMerge")}
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <MediaPreviewDialog item={preview} onOpenChange={(isOpen) => !isOpen && setPreview(null)} />

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={Boolean(pendingDelete)}
        onOpenChange={(isOpen) => (!isOpen ? setPendingDelete(null) : null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("episode.assetDelete")}</DialogTitle>
            <DialogDescription>
              {t("episode.assetDeleteConfirm", { name: pendingDelete?.name ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              disabled={deleting}
              onClick={() => setPendingDelete(null)}
              className="cursor-pointer"
            >
              <X data-icon="inline-start" />
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={deleting}
              onClick={() => void confirmDelete()}
              className="cursor-pointer"
            >
              {deleting ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Trash2 data-icon="inline-start" />
              )}
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
