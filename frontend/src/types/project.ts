import type { VideoCapabilities } from "@/types/auth";

export type SceneTaskStatus = "idle" | "generating" | "success" | "error";

/** One shot inside an episode. Order numbers restart at 1 in every episode. */
export interface Scene {
  id: string;
  episodeId: string | null;
  order: number;
  narration: string;
  /** Spoken by `speakerCharacterId`; `narration` stays the narrator's line. */
  dialogue: string;
  speakerCharacterId: string | null;
  visualPrompt: string;
  shotType: string;
  /** 运镜手法 — how the camera moves through this shot. Reaches the video model. */
  cameraMove: string;
  /** 场景过渡 — how this shot enters from the one before it. */
  transition: string;
  /** The motion prompt. `visualPrompt` describes the frame; this describes the seconds. */
  videoPrompt: string;
  imageReferences: GenerationReferenceInput[];
  videoReferences: GenerationReferenceInput[];
  /** Estimated screen time in ms. 0 means undecided — the project default applies. */
  durationMs: number;
  subtitleText: string;
  /** Who appears in the shot; drives prompt assembly and reference portraits. */
  characterIds: string[];
  /** An approved shot that a batch rerun must leave alone. */
  isLocked: boolean;
  /**
   * Changes only when the server actually changed the row. Key list rows on this rather
   * than on an asset URL: signed links are minted fresh on every response, so a URL-keyed
   * row remounts on every poll and re-downloads its image.
   */
  updatedAt: string;
  image: {
    url: string | null;
    status: SceneTaskStatus;
    progress: number;
  };
  audio: {
    url: string | null;
    status: SceneTaskStatus;
    progress: number;
    duration: number;
  };
  video: {
    url: string | null;
    status: SceneTaskStatus | "idle";
    progress: number;
  };
  /** Last failure reason, persisted so it survives a reload. Empty when the scene is healthy. */
  errorMessage: string;
}

export type EpisodeStatus = "draft" | "storyboard" | "generating" | "done" | "partial" | "failed";

/** An episode without its script or shots: enough to render a switcher or a series list. */
export interface EpisodeSummary {
  id: string;
  projectId: string;
  episodeNumber: number;
  title: string;
  synopsis: string;
  status: EpisodeStatus;
  videoStatus: SceneTaskStatus | "idle";
  videoProgress: number;
  durationMs: number;
  sceneCount: number;
  /** Whether this episode has been anchored yet; the shots are rendered against it. */
  toneImageStatus: SceneTaskStatus | "idle";
  toneImageUrl: string | null;
  errorMessage: string;
  updatedAt: string;
}

export interface Episode extends EpisodeSummary {
  sourceText: string;
  /**
   * The style anchor: a thumbnail grid of every shot, generated in one pass before the
   * full-resolution renders and carried by each of them as a reference. Never a deliverable.
   */
  toneImageUrl: string | null;
  videoUrl: string | null;
  scenes: Scene[];
}

export type ProjectStatus =
  | "idle"
  | "parsing"
  | "generating"
  | "video_generating"
  | "done"
  /** Some shots landed and some failed; retry the failed ones rather than rerunning everything. */
  | "partial"
  | "failed";
export type ProjectMode = "comic" | "drama";
export type ProjectStage = "script" | "bible" | "storyboard" | "audio" | "timeline" | "export";

export interface ProductionSettings {
  mode: ProjectMode;
  aspectRatio: "9:16" | "16:9" | "1:1";
  width: number;
  height: number;
  fps: 24 | 30;
  targetDurationMs: number;
  language: string;
  stylePrompt: string;
  negativePrompt: string;
}

export type ImageResolution = "1K" | "2K" | "4K";
export type GenerationRatio =
  | "auto"
  | "21:9"
  | "16:9"
  | "4:3"
  | "3:2"
  | "1:1"
  | "2:3"
  | "3:4"
  | "9:16"
  | "9:21"
  | "adaptive";
export type VideoQuality = "480p" | "720p" | "1080p" | "2K" | "4K";

/**
 * Which model this series uses for each kind of work, and the parameters every render in
 * it starts from. A null config id means the purpose follows the account default.
 */
export interface ProjectModelSettings {
  textConfigId: number | null;
  imageConfigId: number | null;
  videoConfigId: number | null;
  audioConfigId: number | null;
  imageResolution: ImageResolution;
  imageRatio: GenerationRatio;
  videoQuality: VideoQuality;
  videoAspectRatio: GenerationRatio;
  videoDuration: number;
  videoFps: number;
  videoPromptExtend: boolean;
}

export interface Project {
  id: string;
  title: string;
  /** Shown on the series card. Optional — an empty synopsis renders a placeholder. */
  description: string;
  /** What the user wants the cover to show, in their own words. Drives AI cover generation. */
  coverPrompt: string;
  /** Signed and short-lived, minted per response. Null means "use the fallback cover". */
  coverImageUrl: string | null;
  originalScript: string;
  /** World, tone, and running plot threads, carried into later episodes. */
  seriesBible: string;
  /** The whole cast and every prop, each tiled into one sheet the renderer carries. */
  characterSheetUrl: string | null;
  propSheetUrl: string | null;
  /** Every voice introducing itself, concatenated; a timbre reference for the video model. */
  voiceSheetUrl: string | null;
  status: ProjectStatus;
  videoStatus: SceneTaskStatus | "idle";
  videoProgress: number;
  videoUrl: string | null;
  productionSettings: ProductionSettings;
  modelSettings: ProjectModelSettings;
  currentStage: ProjectStage;
  /** The episode `scenes` belongs to. Null only for a series with no episode yet. */
  currentEpisodeId: string | null;
  episodes: EpisodeSummary[];
  updatedAt: string;
  /** The current episode's shots, never the whole series': order numbers restart each episode. */
  scenes: Scene[];
}

export interface ProjectItemResponse {
  project: Project;
}

export interface ProjectListResponse {
  projects: Project[];
}

export interface CreateProjectInput {
  title?: string;
  description?: string;
  coverPrompt?: string;
  originalScript?: string;
  productionSettings?: Partial<ProductionSettings>;
}

export interface UpdateProjectInput {
  title?: string;
  description?: string;
  coverPrompt?: string;
  originalScript?: string;
  seriesBible?: string;
  /**
   * Send only what changed. A config id of `0` clears the pick and returns that purpose to
   * the account default — `null` cannot mean "clear", because in a PATCH it already means
   * "leave alone".
   */
  modelSettings?: Partial<ProjectModelSettings>;
}

export interface SetProjectCoverInput {
  /** A `data:image/png|jpeg|webp;base64,` string. The API never takes multipart. */
  imageData: string;
}

/**
 * Cover generation is project-less on purpose: the create dialog runs it before a project
 * exists, and the edit dialog runs it on unsaved edits. It never writes — the caller
 * previews the result and applies it with `setProjectCoverAction`.
 */
export interface GenerateCoverInput {
  /** What the cover should show. Required — this is the subject of the picture. */
  prompt: string;
  title?: string;
  stylePrompt?: string;
}

export interface GenerateCoverResponse {
  imageData: string;
}

/** One resolved model, with the limits the UI must not let the user exceed. */
export interface ProjectModelSummary {
  provider: string;
  model: string;
  source: string;
  configId: number | null;
  /** False when this purpose is falling through to the account default. */
  isProjectPick: boolean;
  capabilities?: {
    maxReferenceImages?: number;
    resolutions?: ImageResolution[];
    ratios?: GenerationRatio[];
  } | null;
}

export interface ProjectModelsResponse {
  models: {
    text: ProjectModelSummary | null;
    image: ProjectModelSummary | null;
    video: (ProjectModelSummary & { capabilities: VideoCapabilities | null }) | null;
    audio: ProjectModelSummary | null;
  };
  modelSettings: ProjectModelSettings;
}

export interface PromptPreset {
  key: string;
  label: string;
  template: string;
}

export interface PromptPresetListResponse {
  kind: string;
  presets: PromptPreset[];
}

export interface CreateEpisodeInput {
  /** Required: a list of "第 1 集 / 第 2 集" tells the user nothing. */
  title: string;
  synopsis?: string;
  sourceText?: string;
}

/** Which half of the storyboard a breakdown produces. */
export type BreakdownTarget = "shots" | "video" | "both";

/**
 * What the breakdown may look at. Selecting nothing is meaningful: it tells the model to
 * decide everything from the script alone. Characters the bible has never heard of are
 * inferred from the script either way.
 */
export interface BreakdownReferences {
  characterIds?: string[];
  propIds?: string[];
  voiceProfileIds?: string[];
  useCastSheet?: boolean;
  usePropSheet?: boolean;
  useVoiceSheet?: boolean;
}

export interface BreakdownEpisodeInput {
  target: BreakdownTarget;
  script?: string;
  references?: BreakdownReferences;
  /** Re-splitting discards rendered shots; the first call reports, this confirms. */
  replaceAll?: boolean;
  model?: string;
}

export interface BreakdownEpisodeResponse {
  projectId: string;
  episodeId: string;
  target: BreakdownTarget;
  applied: boolean;
  discardsGeneratedScenes: number;
  shotCount?: number;
  scenes: Scene[];
}

/** Anchor an episode's look without rendering any shots against it yet. */
export interface GenerateToneSheetInput {
  previousEpisodeId?: string;
  mergeReferences?: boolean;
  regenerate?: boolean;
  references?: GenerationReferenceInput[];
}

export interface GenerateToneSheetResponse {
  projectId: string;
  episodeId: string;
  status: ProjectStatus;
  regeneratesToneSheet: boolean;
}

export interface CancelProjectRunResponse {
  projectId: string;
  canceled: boolean;
  status: ProjectStatus;
}

/**
 * Render an episode: one tone sheet to anchor the look, then a frame per shot.
 *
 * `mergeReferences` trades tokens for fidelity — merged, the cast sheet, prop sheet, and
 * previous anchor arrive as one image; separate, they cost more. `regenerate` resamples the
 * anchor instead of reusing it, which also restyles shots that were already approved.
 */
export interface GenerateStoryboardInput {
  previousEpisodeId?: string;
  mergeReferences?: boolean;
  regenerate?: boolean;
  sceneIds?: string[];
  references?: GenerationReferenceInput[];
  /**
   * Render only the shots that are not already rendered. What "retry the failed ones" means:
   * without it a rerun re-renders, and re-pays for, every unlocked shot in the episode.
   */
  pendingOnly?: boolean;
}

export type GenerationReferenceKind = "character" | "characterState" | "prop" | "tone" | "sceneImage" | "sceneVideo" | "voice";

export interface GenerationReferenceInput {
  kind: GenerationReferenceKind;
  id: string;
}

export interface GenerateStoryboardResponse {
  projectId: string;
  episodeId: string;
  status: ProjectStatus;
  shotCount: number;
  referenceCount: number;
  mergeReferences: boolean;
  regeneratesToneSheet: boolean;
}

export interface UpdateEpisodeInput {
  title?: string;
  synopsis?: string;
  sourceText?: string;
  status?: EpisodeStatus;
}

export interface EpisodeListResponse {
  episodes: EpisodeSummary[];
}

export interface EpisodeItemResponse {
  episode: Episode;
}

/**
 * One look a character can appear in: an age, an outfit, a transformation. States are
 * parallel forms of the same person, not a timeline — an episode range is an optional
 * narrowing, and a state that leaves it unset is simply always available.
 */
export interface CharacterState {
  id: string;
  characterId: string;
  name: string;
  /** What this state is ("十六岁，校服"); feeds the model that drafts `finalPrompt`. */
  description: string;
  /** Empty means "the look did not change"; the card's own prompt still applies. */
  appearancePrompt: string;
  /** The reviewed prompt that actually draws the sheet. Shown in the UI simply as 提示词. */
  finalPrompt: string;
  /** The turnaround sheet: front, three-quarter, and profile in one image. */
  referenceImageUrl: string | null;
  voiceModel: string;
  orderNum: number;
  /** Null on either means the state is not pinned to an episode range at all. */
  fromEpisode: number | null;
  toEpisode: number | null;
  updatedAt: string;
}

/** A recurring cast member, pinned to one look, one image model, and one voice. */
export interface Character {
  id: string;
  projectId: string;
  name: string;
  /** Comma-separated names the script also uses for this character. */
  aliases: string;
  description: string;
  appearancePrompt: string;
  /** Legacy card portrait from before looks were split into states; nothing writes it. */
  referenceImageUrl: string | null;
  /** Every state of this character tiled into one image. */
  sheetImageUrl: string | null;
  /** Frozen when the first image was drawn, so a later default change cannot restyle them. */
  imageProvider: string;
  imageModel: string;
  voiceProvider: string;
  voiceModel: string;
  /** The bound voice profile, if any; it wins over the two columns above. */
  voiceProfileId: string | null;
  /** Set once the look is approved; a locked card is never redrawn. */
  isLocked: boolean;
  orderNum: number;
  states: CharacterState[];
  updatedAt: string;
}

export interface CreateCharacterInput {
  name: string;
  aliases?: string;
  description?: string;
  appearancePrompt?: string;
  voiceProvider?: string;
  voiceModel?: string;
  orderNum?: number;
}

export interface UpdateCharacterInput {
  name?: string;
  aliases?: string;
  description?: string;
  appearancePrompt?: string;
  voiceProvider?: string;
  voiceModel?: string;
  /** "" unbinds. Not null: the backend reads an absent field as "leave it alone". */
  voiceProfileId?: string;
  isLocked?: boolean;
  orderNum?: number;
}

export interface CreateCharacterStateInput {
  name: string;
  description?: string;
  appearancePrompt?: string;
  finalPrompt?: string;
  voiceModel?: string;
  orderNum?: number;
  fromEpisode?: number | null;
  toEpisode?: number | null;
}

export type UpdateCharacterStateInput = Partial<CreateCharacterStateInput>;

/**
 * Draft an image prompt for review. The fields come from the dialog rather than the stored
 * row so drafting works against edits the user has not saved yet. The instruction template
 * is the built-in one and is not overridable; `preset` picks which built-in to draft from.
 */
export interface DraftPromptInput {
  name?: string;
  description?: string;
  preset?: string;
  model?: string;
}

export interface DraftPromptResponse {
  prompt: string;
}

/** Empty falls back to the stored `finalPrompt`. */
export interface GenerateReferenceImageInput {
  prompt?: string;
}

export interface UploadReferenceImageInput {
  /** A `data:image/png|jpeg|webp;base64,` string. The API never takes multipart. */
  imageData: string;
}

export interface CharacterListResponse {
  characters: Character[];
}

export interface CharacterItemResponse {
  character: Character;
}

export interface CharacterStateItemResponse {
  state: CharacterState;
}

export interface CastSheetResponse {
  characterSheetUrl: string | null;
}

/** One voice in the show: the narrator, or a character's timbre. */
export interface VoiceProfile {
  id: string;
  projectId: string;
  name: string;
  /** Free-text note for the user ("沙哑，压低"); never sent to a provider. */
  note: string;
  /** A provider and a model, never credentials — those live on the account's audio config. */
  voiceProvider: string;
  voiceModel: string;
  /** The line this voice says in the merged track; the wording tells the model when to use it. */
  sampleText: string;
  audioUrl: string | null;
  orderNum: number;
  updatedAt: string;
}

export interface CreateVoiceProfileInput {
  name: string;
  note?: string;
  voiceProvider?: string;
  voiceModel?: string;
  sampleText?: string;
  orderNum?: number;
}

export type UpdateVoiceProfileInput = Partial<CreateVoiceProfileInput>;

/**
 * Design a timbre from a description and bind it to this series in one step. Provider and
 * model come from the project's audio configuration, never from the client.
 */
export interface DesignVoiceProfileInput {
  name: string;
  voicePrompt: string;
  /** What the audition says. Distinct from `sampleText`, the line in the merged track. */
  previewText: string;
  note?: string;
  sampleText?: string;
}

/** Bind a timbre already saved on the account to this series. */
export interface ImportVoiceProfileInput {
  userVoiceId: string;
  name?: string;
  note?: string;
  sampleText?: string;
}

export interface VoiceProfileListResponse {
  voices: VoiceProfile[];
}

export interface VoiceProfileItemResponse {
  voice: VoiceProfile;
}

export interface VoiceSheetResponse {
  voiceSheetUrl: string | null;
}

/** An object the series has to draw the same way every time it appears. */
export interface Prop {
  id: string;
  projectId: string;
  name: string;
  description: string;
  /** Whose prop it is; printed on the reference image. Null leaves it unattributed. */
  ownerCharacterId: string | null;
  /** Resolved by the server so a card can render the owner without a second request. */
  ownerName: string;
  /** The reviewed prompt that actually draws the image. Shown in the UI simply as 提示词. */
  finalPrompt: string;
  imageUrl: string | null;
  orderNum: number;
  updatedAt: string;
}

export interface CreatePropInput {
  name: string;
  description?: string;
  /** "" leaves it unattributed. Not null: an absent field means "leave alone" in a PATCH. */
  ownerCharacterId?: string;
  finalPrompt?: string;
  orderNum?: number;
}

export type UpdatePropInput = Partial<CreatePropInput>;

export interface PropListResponse {
  props: Prop[];
}

export interface PropItemResponse {
  prop: Prop;
}

export interface PropSheetResponse {
  propSheetUrl: string | null;
}

export interface SetSceneCastInput {
  characterIds: string[];
}

export interface SetSceneCastResponse {
  sceneId: string;
  characterIds: string[];
}

export type UpdateProductionSettingsInput = Partial<ProductionSettings> & {
  currentStage?: ProjectStage;
};

export type GenerationJobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export interface GenerationJob {
  id: string;
  projectId: string;
  sceneId: string | null;
  jobType: "storyboards" | "audio" | "videos" | "preview" | "export";
  status: GenerationJobStatus;
  progress: number;
  attempt: number;
  maxAttempts: number;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface GenerationJobListResponse {
  jobs: GenerationJob[];
}

export interface UpdateSceneInput {
  narration?: string;
  dialogue?: string;
  speakerCharacterId?: string;
  visualPrompt?: string;
  shotType?: string;
  cameraMove?: string;
  transition?: string;
  videoPrompt?: string;
  imageReferences?: GenerationReferenceInput[];
  videoReferences?: GenerationReferenceInput[];
  durationMs?: number;
  subtitleText?: string;
  isLocked?: boolean;
}
export interface CreateSceneInput extends UpdateSceneInput {
  episodeId?: string;
}
export interface ReorderScenesInput {
  sceneIds: string[];
  /** Order numbers restart each episode, so a reorder is always within one. */
  episodeId?: string;
}

export interface ParseProjectInput {
  script: string;
  model?: string;
  /** Which episode the parsed shots land in. Omitted means the current one. */
  episodeId?: string;
  /**
   * Reparsing discards generated shots. Without this the backend returns a preview
   * (`applied: false`) so the user can confirm before losing rendered work.
   */
  replaceAll?: boolean;
}

/** A parsed shot that has not been written to the project yet. */
export interface PendingScene {
  order: number;
  narration: string;
  visualPrompt: string;
}

export interface ParseProjectResponse {
  projectId: string;
  episodeId: string;
  status: ProjectStatus;
  source: "llm" | "fallback";
  warning?: string;
  applied: boolean;
  discardsGeneratedScenes: number;
  pendingScenes: PendingScene[];
  scenes: Scene[];
}

export interface GenerateProjectInput {
  model?: string;
  episodeId?: string;
  sceneIds?: string[];
  /** See `GenerateStoryboardInput.pendingOnly`. */
  pendingOnly?: boolean;
}

export interface GenerateProjectResponse {
  projectId: string;
  episodeId: string;
  status: ProjectStatus;
  sceneCount: number;
  model?: string;
  provider?: string;
  imageModel?: string;
}

export interface OptimizeProjectInput {
  script?: string;
  model?: string;
}

export interface OptimizeProjectResponse {
  projectId: string;
  optimizedScript: string;
  tips: string[];
  source: "llm" | "fallback";
  warning?: string;
  appliedToProject: boolean;
}

export interface GenerateVideoInput {
  model?: string;
  episodeId?: string;
  quality?: string;
  aspectRatio?: string;
  fps?: number;
  duration?: number;
  promptExtend?: boolean;
  /**
   * Pass the project's merged timbre reference. Costs more, and a model that does not accept
   * reference audio returns 400 rather than silently dropping it.
   */
  withAudio?: boolean;
  sceneIds?: string[];
  references?: GenerationReferenceInput[];
  /** See `GenerateStoryboardInput.pendingOnly`. A clip is the costliest thing to redo. */
  pendingOnly?: boolean;
}

export interface GenerateVideoResponse {
  projectId: string;
  status: ProjectStatus;
  model: string;
  episodeId: string;
  sceneCount: number;
  withAudio: boolean;
}

export type ExportStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

/** Several rendered shots merged into one file. Order follows the request, not shot number. */
export interface ExportJob {
  id: string;
  projectId: string;
  sceneIds: string[];
  rangeLabel: string;
  status: ExportStatus;
  progress: number;
  videoUrl: string | null;
  fileSize: number;
  errorMessage: string;
  createdAt: string;
  updatedAt: string;
  finishedAt: string | null;
}

export interface CreateExportInput {
  /** Ordered: the video section assembles a cut, which need not follow the storyboard. */
  sceneIds: string[];
  rangeLabel?: string;
}

export interface ExportListResponse {
  exports: ExportJob[];
}

export interface ExportItemResponse {
  export: ExportJob;
}

export interface SceneUpdatePayload {
  episodeId?: string;
  narration?: string;
  dialogue?: string;
  speakerCharacterId?: string | null;
  characterIds?: string[];
  visualPrompt?: string;
  shotType?: string;
  cameraMove?: string;
  durationMs?: number;
  subtitleText?: string;
  isLocked?: boolean;
  order?: number;
  parseStatus?: string;
  imageStatus?: SceneTaskStatus;
  imageProgress?: number;
  imageUrl?: string | null;
  audioStatus?: SceneTaskStatus;
  audioProgress?: number;
  audioUrl?: string | null;
  audioDuration?: number;
  videoStatus?: SceneTaskStatus | "idle";
  videoProgress?: number;
  videoUrl?: string | null;
  videoModel?: string;
  errorMsg?: string;
}
