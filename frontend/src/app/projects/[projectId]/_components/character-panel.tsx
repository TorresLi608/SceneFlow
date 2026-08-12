"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Image as ImageIcon, Lock, LockOpen, Plus, Trash2, UserPlus, WandSparkles } from "lucide-react";
import Image from "next/image";

import {
  createCharacterAction,
  createCharacterVariantAction,
  deleteCharacterAction,
  deleteCharacterVariantAction,
  generateCharacterPortraitAction,
  listCharactersAction,
  updateCharacterAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { backendBaseURL } from "@/lib/http/backend-client";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { Character, UpdateCharacterInput } from "@/types/project";

interface CharacterPanelProps {
  projectId: string;
  /** Reported upward so the workbench keeps one status line rather than two. */
  onStatus: (message: string | null) => void;
  /** Lets the open storyboard drop a character it had cast. */
  onCharacterDeleted: (characterId: string) => void;
}

interface VariantDraft {
  name: string;
  appearancePrompt: string;
  fromEpisode: string;
}

const EMPTY_VARIANT: VariantDraft = { name: "", appearancePrompt: "", fromEpisode: "" };

function resolveImageURL(url: string | null) {
  return url && url.startsWith("/") ? `${backendBaseURL}${url}` : url;
}

interface CharacterRowProps {
  character: Character;
  portraitPending: boolean;
  onSave: (patch: UpdateCharacterInput) => void;
  onDrawPortrait: () => void;
  onDelete: () => void;
  onAddVariant: (draft: { name: string; appearancePrompt: string; fromEpisode: number }) => void;
  onDeleteVariant: (variantId: string) => void;
}

function CharacterRow({
  character,
  portraitPending,
  onSave,
  onDrawPortrait,
  onDelete,
  onAddVariant,
  onDeleteVariant,
}: CharacterRowProps) {
  const { t } = useI18n();
  // Text fields are held locally and written on blur: saving per keystroke would be one
  // request per character per letter. Seeded once on mount and deliberately not re-synced
  // from the server — a refetch landing mid-sentence would wipe what is being typed.
  const [draft, setDraft] = useState({
    name: character.name,
    appearancePrompt: character.appearancePrompt,
    voiceModel: character.voiceModel,
  });
  const [variant, setVariant] = useState<VariantDraft>(EMPTY_VARIANT);

  const commit = (field: keyof typeof draft, current: string) => {
    // Trimmed here because the backend trims too, and an untrimmed draft would keep
    // looking different from what was actually saved.
    const value = draft[field].trim();
    if (value !== draft[field]) {
      setDraft((state) => ({ ...state, [field]: value }));
    }
    if (value !== current) {
      onSave({ [field]: value } as UpdateCharacterInput);
    }
  };

  const portrait = resolveImageURL(character.referenceImageUrl);

  return (
    <div className="space-y-3 rounded-lg border border-border/80 bg-muted/20 p-3">
      <div className="flex flex-wrap items-start gap-3">
        <div className="relative size-20 shrink-0 overflow-hidden rounded-md border border-border/70 bg-muted">
          {portrait ? (
            <Image src={portrait} alt={character.name} fill unoptimized sizes="80px" className="object-cover" />
          ) : (
            <div className="flex size-full items-center justify-center text-muted-foreground">
              <ImageIcon className="size-5" />
            </div>
          )}
        </div>

        <div className="min-w-52 flex-1 space-y-2">
          <Input
            value={draft.name}
            onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
            onBlur={() => commit("name", character.name)}
            className="font-medium"
            aria-label={t("bible.name")}
          />
          <div className="flex flex-wrap items-center gap-2">
            {character.isLocked ? (
              <Badge variant="outline" className="gap-1">
                <Lock className="size-3.5" />
                {t("bible.locked")}
              </Badge>
            ) : null}
            {character.imageModel ? <Badge variant="secondary">{character.imageModel}</Badge> : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={onDrawPortrait}
            disabled={character.isLocked || portraitPending}
          >
            <WandSparkles className="mr-1 size-4" />
            {portraitPending
              ? t("bible.portraitRunningShort")
              : portrait
                ? t("bible.portraitRedraw")
                : t("bible.portraitDraw")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onSave({ isLocked: !character.isLocked })}>
            {character.isLocked ? <LockOpen className="mr-1 size-4" /> : <Lock className="mr-1 size-4" />}
            {character.isLocked ? t("bible.unlock") : t("bible.lock")}
          </Button>
          <Button size="sm" variant="ghost" className="text-muted-foreground" onClick={onDelete}>
            <Trash2 className="mr-1 size-4" />
            {t("common.delete")}
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`appearance_${character.id}`}>{t("bible.appearance")}</Label>
          <Textarea
            id={`appearance_${character.id}`}
            value={draft.appearancePrompt}
            onChange={(event) => setDraft((current) => ({ ...current, appearancePrompt: event.target.value }))}
            onBlur={() => commit("appearancePrompt", character.appearancePrompt)}
            className="min-h-16"
            placeholder={t("bible.appearancePlaceholder")}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`voice_${character.id}`}>{t("bible.voice")}</Label>
          <Input
            id={`voice_${character.id}`}
            value={draft.voiceModel}
            onChange={(event) => setDraft((current) => ({ ...current, voiceModel: event.target.value }))}
            onBlur={() => commit("voiceModel", character.voiceModel)}
            placeholder="zh-CN-YunxiNeural"
          />
          {/* A card holds no credentials, so an override only applies on the provider the
              project is already configured for. */}
          <p className="text-xs text-muted-foreground">{t("bible.voiceHint")}</p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">{t("bible.variants")}</p>
        {character.variants.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("bible.variantsEmpty")}</p>
        ) : (
          <div className="space-y-1">
            {character.variants.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-center gap-2 rounded-md border border-border/70 bg-background/60 px-2 py-1.5 text-xs"
              >
                <Badge variant="outline">
                  {item.toEpisode === null
                    ? t("bible.variantFrom", { from: item.fromEpisode })
                    : t("bible.variantRange", { from: item.fromEpisode, to: item.toEpisode })}
                </Badge>
                <span className="font-medium">{item.name}</span>
                <span className="text-muted-foreground">{item.appearancePrompt}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto h-7 px-2 text-muted-foreground"
                  onClick={() => onDeleteVariant(item.id)}
                  aria-label={t("common.delete")}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Input
            value={variant.name}
            onChange={(event) => setVariant((current) => ({ ...current, name: event.target.value }))}
            placeholder={t("bible.variantNamePlaceholder")}
            className="max-w-40"
          />
          <Input
            value={variant.appearancePrompt}
            onChange={(event) => setVariant((current) => ({ ...current, appearancePrompt: event.target.value }))}
            placeholder={t("bible.variantAppearancePlaceholder")}
            className="max-w-72 flex-1"
          />
          <Input
            type="number"
            min={1}
            value={variant.fromEpisode}
            onChange={(event) => setVariant((current) => ({ ...current, fromEpisode: event.target.value }))}
            placeholder={t("bible.variantFromPlaceholder")}
            className="max-w-28"
          />
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              onAddVariant({
                name: variant.name.trim(),
                appearancePrompt: variant.appearancePrompt.trim(),
                fromEpisode: Math.max(1, Number(variant.fromEpisode) || 1),
              });
              setVariant(EMPTY_VARIANT);
            }}
            disabled={!variant.name.trim()}
          >
            <Plus className="mr-1 size-4" />
            {t("bible.variantAdd")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function CharacterPanel({ projectId, onStatus, onCharacterDeleted }: CharacterPanelProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");

  const charactersQuery = useQuery({
    queryKey: queryKeys.characters(projectId),
    queryFn: () => listCharactersAction(projectId),
    enabled: Boolean(projectId),
  });

  const characters = charactersQuery.data?.characters ?? [];
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) });

  const addMutation = useMutation({
    mutationFn: (name: string) => createCharacterAction(projectId, { name }),
    onSuccess: (response) => {
      setNewName("");
      void refresh();
      onStatus(t("bible.added", { name: response.character.name }));
    },
    onError: (error) => onStatus(resolveRequestError(error, t("bible.addFailed"))),
  });

  const updateMutation = useMutation({
    mutationFn: (params: { characterId: string; patch: UpdateCharacterInput }) =>
      updateCharacterAction(projectId, params.characterId, params.patch),
    onSuccess: () => void refresh(),
    onError: (error) => onStatus(resolveRequestError(error, t("bible.saveFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: (characterId: string) => deleteCharacterAction(projectId, characterId),
    onSuccess: (_, characterId) => {
      onCharacterDeleted(characterId);
      void refresh();
      onStatus(t("bible.deleted"));
    },
    onError: (error) => onStatus(resolveRequestError(error, t("bible.deleteFailed"))),
  });

  const portraitMutation = useMutation({
    mutationFn: (characterId: string) => generateCharacterPortraitAction(projectId, characterId),
    onMutate: () => onStatus(t("bible.portraitRunning")),
    onSuccess: () => {
      void refresh();
      onStatus(t("bible.portraitDone"));
    },
    onError: (error) => onStatus(resolveRequestError(error, t("bible.portraitFailed"))),
  });

  const addVariantMutation = useMutation({
    mutationFn: (params: { characterId: string; name: string; appearancePrompt: string; fromEpisode: number }) =>
      createCharacterVariantAction(projectId, params.characterId, {
        name: params.name,
        appearancePrompt: params.appearancePrompt,
        fromEpisode: params.fromEpisode,
      }),
    onSuccess: () => void refresh(),
    onError: (error) => onStatus(resolveRequestError(error, t("bible.variantAddFailed"))),
  });

  const deleteVariantMutation = useMutation({
    mutationFn: (params: { characterId: string; variantId: string }) =>
      deleteCharacterVariantAction(projectId, params.characterId, params.variantId),
    onSuccess: () => void refresh(),
    onError: (error) => onStatus(resolveRequestError(error, t("bible.variantDeleteFailed"))),
  });

  return (
    <Card className="border-border/80">
      <CardHeader className="space-y-1">
        <CardTitle className="text-base">{t("bible.title")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("bible.hint")}</p>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder={t("bible.namePlaceholder")}
            className="max-w-60"
          />
          <Button
            variant="secondary"
            onClick={() => addMutation.mutate(newName.trim())}
            disabled={!newName.trim() || addMutation.isPending}
          >
            <UserPlus className="mr-2 size-4" />
            {t("bible.add")}
          </Button>
        </div>

        {charactersQuery.isLoading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : characters.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t("bible.empty")}</p>
        ) : (
          <div className="space-y-3">
            {characters.map((character) => (
              <CharacterRow
                key={character.id}
                character={character}
                portraitPending={portraitMutation.isPending && portraitMutation.variables === character.id}
                onSave={(patch) => updateMutation.mutate({ characterId: character.id, patch })}
                onDrawPortrait={() => portraitMutation.mutate(character.id)}
                onDelete={() => deleteMutation.mutate(character.id)}
                onAddVariant={(draft) => addVariantMutation.mutate({ characterId: character.id, ...draft })}
                onDeleteVariant={(variantId) =>
                  deleteVariantMutation.mutate({ characterId: character.id, variantId })
                }
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
