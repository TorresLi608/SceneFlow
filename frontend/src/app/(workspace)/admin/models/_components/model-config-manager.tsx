"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  Coins,
  Cpu,
  Eye,
  EyeOff,
  Globe,
  ImageIcon,
  Layers,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import {
  createOfficialConfigAction,
  deleteOfficialConfigAction,
  getModelConfigSecretAction,
  listOfficialConfigsAction,
  updateModelConfigAction,
  updateOfficialConfigAction,
} from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import {
  activateOfficialConfigAction,
  createUserConfigAction,
  deleteUserConfigAction,
  discoverModelsAction,
  getUserConfigSecretAction,
  getVideoModelCatalogAction,
  listUserConfigsAction,
  updateUserConfigAction,
} from "@/actions/settings-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { ModelSeriesCombobox } from "@/components/model-series-combobox";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  type ConnectionMode,
  baseUrlForConnection,
  connectionModeFromConfig,
  configsByPurpose,
  defaultProviderOption,
  isRelayConnection,
  providerLabel,
  providerOption,
  providerOptions,
} from "@/lib/model-providers";
import { useUserStore } from "@/store/user-store";
import type { ConfigPurpose, UserConfig, VideoCapabilities } from "@/types/auth";

const videoQualityOptions: VideoCapabilities["qualities"] = [
  "480p",
  "720p",
  "1080p",
  "2K",
  "4K",
];
const videoAspectRatioOptions: VideoCapabilities["aspectRatios"] = [
  "21:9",
  "16:9",
  "4:3",
  "1:1",
  "3:4",
  "9:16",
  "adaptive",
];

function defaultVideoCapabilities(provider: string, model = ""): VideoCapabilities {
  const normalized = model.toLowerCase();
  if (provider === "doubao" && normalized.startsWith("doubao-seedance")) {
    const is25 = normalized.includes("2.5");
    return {
      qualities: is25 ? ["480p", "720p", "1080p"] : normalized.includes("fast") || normalized.includes("mini") ? ["480p", "720p"] : ["480p", "720p", "1080p", "4K"],
      fps: [],
      aspectRatios: ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"],
      promptExtend: false,
      minDuration: 4,
      maxDuration: is25 ? 30 : 15,
      referenceImages: true,
      referenceImagesRequired: false,
      maxReferenceImages: is25 ? 30 : 9,
      referenceVideo: true,
      maxReferenceVideos: is25 ? 10 : 3,
      referenceVideosRequired: false,
      referenceAudio: true,
      maxReferenceAudios: is25 ? 10 : 3,
      referenceAudiosRequired: false,
      audioParam: "with_audio",
      audioDefault: true,
      supportsFirstFrame: true,
      supportsLastFrame: true,
      supportsStartEndFrames: true,
    };
  }
  if (provider === "qwen" && (normalized === "wan2.7" || normalized.startsWith("wan2.7-r2v"))) {
    return {
      qualities: ["720p", "1080p"],
      fps: [],
      aspectRatios: ["16:9", "9:16", "1:1", "4:3", "3:4"],
      promptExtend: true,
      minDuration: 2,
      maxDuration: 15,
      referenceImages: true,
      referenceImagesRequired: false,
      maxReferenceImages: 5,
      referenceVideo: true,
      maxReferenceVideos: 1,
      referenceVideosRequired: false,
      referenceAudio: true,
      maxReferenceAudios: 1,
      referenceAudiosRequired: false,
      audioParam: "reference_voice",
      audioDefault: false,
      supportsFirstFrame: true,
      supportsLastFrame: false,
      supportsStartEndFrames: false,
    };
  }
  if (provider === "qwen" && normalized.startsWith("wan3.0")) {
    return {
      qualities: ["480p", "720p", "1080p"],
      fps: [],
      aspectRatios: ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"],
      promptExtend: true,
      minDuration: 2,
      maxDuration: 30,
      referenceImages: true,
      referenceImagesRequired: false,
      maxReferenceImages: 10,
      referenceVideo: true,
      maxReferenceVideos: 5,
      referenceVideosRequired: false,
      referenceAudio: true,
      maxReferenceAudios: 5,
      referenceAudiosRequired: false,
      audioParam: "audio",
      audioDefault: true,
      supportsFirstFrame: true,
      supportsLastFrame: true,
      supportsStartEndFrames: false,
    };
  }
  const isI2v = model.includes("-i2v");
  const isR2v = model.includes("-r2v");
  const isVideoEdit = model.includes("videoedit");
  return provider === "qwen"
    ? {
        qualities: videoQualityOptions,
        fps: [],
        aspectRatios: videoAspectRatioOptions,
        promptExtend: isI2v,
        minDuration: isI2v ? 2 : 3,
        maxDuration: 15,
        referenceImages: isI2v || isR2v,
        referenceImagesRequired: isI2v || isR2v,
        maxReferenceImages: isR2v ? 5 : isI2v || isVideoEdit ? 1 : 0,
        referenceVideo: isVideoEdit,
        maxReferenceVideos: isVideoEdit ? 1 : 0,
        referenceVideosRequired: false,
        referenceAudio: isI2v,
        maxReferenceAudios: isI2v ? 1 : 0,
        referenceAudiosRequired: false,
      }
    : {
        qualities: videoQualityOptions,
        fps: [24],
        aspectRatios:
          provider === "gemini"
            ? videoAspectRatioOptions.filter((value) => value !== "1:1")
            : videoAspectRatioOptions,
        promptExtend: false,
        minDuration: 3,
        maxDuration: 15,
        referenceImages: false,
        referenceImagesRequired: false,
        maxReferenceImages: 0,
        referenceVideo: false,
        maxReferenceVideos: 0,
        referenceVideosRequired: false,
        referenceAudio: false,
        maxReferenceAudios: 0,
        referenceAudiosRequired: false,
      };
}

function editableVideoCapabilities(config: UserConfig): VideoCapabilities {
  const defaults = defaultVideoCapabilities(config.provider, config.modelSeries);
  const current = config.videoCapabilities as
    | (Partial<VideoCapabilities> & {
        resolutions?: string[];
        drivingAudio?: boolean;
      })
    | null;
  if (!current) return defaults;
  const aspectByResolution: Record<string, VideoCapabilities["aspectRatios"][number]> = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "1024x1024": "1:1",
    "1920x1080": "16:9",
  };
  const aspectRatios =
    current.aspectRatios ?? [
      ...new Set(
        current.resolutions?.flatMap((value) =>
          aspectByResolution[value] ? [aspectByResolution[value]] : []
        ) ?? []
      ),
    ];
  const maxReferenceImages = current.maxReferenceImages ?? 0;
  const referenceVideo = current.referenceVideo ?? false;
  const referenceAudio = current.referenceAudio ?? current.drivingAudio ?? false;
  return {
    ...defaults,
    ...current,
    aspectRatios,
    referenceImages: current.referenceImages ?? maxReferenceImages > 0,
    maxReferenceImages,
    referenceVideo,
    maxReferenceVideos: current.maxReferenceVideos ?? (referenceVideo ? 1 : 0),
    referenceAudio,
    maxReferenceAudios: current.maxReferenceAudios ?? (referenceAudio ? 1 : 0),
    supportsFirstFrame: current.supportsFirstFrame ?? defaults.supportsFirstFrame,
    supportsLastFrame: current.supportsLastFrame ?? defaults.supportsLastFrame,
  };
}

const pageSize = 10;
const emptyConfigs: UserConfig[] = [];

type SourceFilter = "all" | "official" | "user";
type DefaultFilter = "all" | "default" | "not-default";
type EnabledFilter = "all" | "enabled" | "disabled";

function configTitle(
  config: UserConfig,
  purposeLabel: Record<ConfigPurpose, string>,
  t: (key: string) => string
) {
  return config.name || `${purposeLabel[config.purpose]} · ${providerLabel(config.provider, t)}`;
}

function rowKey(config: UserConfig) {
  return `${config.source}:${config.id}`;
}

function isDefaultConfig(
  config: UserConfig,
  activeUserByPurpose: Partial<Record<ConfigPurpose, UserConfig>>
) {
  if (config.source === "user") {
    return config.isActive;
  }
  return !activeUserByPurpose[config.purpose] && config.isActive;
}

function defaultPricingUnit(purpose: ConfigPurpose): UserConfig["unitName"] {
  if (purpose === "image") return "image";
  if (purpose === "video") return "second";
  if (purpose === "audio") return "request";
  return "token";
}

export function ModelConfigManager() {
  const { t, formatDateTime } = useI18n();
  const queryClient = useQueryClient();
  const defaultOption = defaultProviderOption();
  const user = useUserStore((state) => state.user);
  const isSuperAdmin = user?.role === "superAdmin";

  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [purposeFilter, setPurposeFilter] = useState<"all" | ConfigPurpose>("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [defaultFilter, setDefaultFilter] = useState<DefaultFilter>("all");
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>("all");
  const [page, setPage] = useState(1);
  const [viewingConfig, setViewingConfig] = useState<UserConfig | null>(null);
  const [editingConfig, setEditingConfig] = useState<UserConfig | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [deletingConfig, setDeletingConfig] = useState<UserConfig | null>(null);

  // 表单状态
  const [isOfficial, setIsOfficial] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [purpose, setPurpose] = useState<ConfigPurpose>("script");
  const [provider, setProvider] = useState(defaultOption.value);
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("direct");
  const [baseUrl, setBaseUrl] = useState(defaultOption.baseUrl ?? "");
  const [modelSeries, setModelSeries] = useState(defaultOption.modelSeries);
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [isEnabled, setIsEnabled] = useState(true);
  const [isDefault, setIsDefault] = useState(false);
  const [pricingMultiplier, setPricingMultiplier] = useState("1");
  const [inputPricePerMillion, setInputPricePerMillion] = useState("0");
  const [outputPricePerMillion, setOutputPricePerMillion] = useState("0");
  const [cacheReadPricePerMillion, setCacheReadPricePerMillion] = useState("0");
  const [cacheWritePricePerMillion, setCacheWritePricePerMillion] = useState("0");
  const [unitPrice, setUnitPrice] = useState("0");
  const [imageMaxReferenceImages, setImageMaxReferenceImages] = useState(4);
  const [videoCapabilities, setVideoCapabilities] = useState<VideoCapabilities>(
    defaultVideoCapabilities(defaultOption.value)
  );

  const purposeLabel: Record<ConfigPurpose, string> = {
    general: t("settings.generalPurpose"),
    script: t("settings.scriptPurpose"),
    image: t("settings.imagePurpose"),
    video: t("settings.videoPurpose"),
    audio: t("settings.audioPurpose"),
  };

  const officialQuery = useQuery({
    queryKey: queryKeys.officialConfigs,
    queryFn: listOfficialConfigsAction,
    enabled: isSuperAdmin,
  });
  const userQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
  });
  const videoModelsQuery = useQuery({ queryKey: queryKeys.videoModelCatalog, queryFn: getVideoModelCatalogAction });
  const videoCatalog = videoModelsQuery.data?.models ?? [];
  // Suggestions, not a whitelist. Doubao's base URL is passed through unchanged so relays
  // serve their own model ids, and locking the field to the catalog would make those
  // unconfigurable — as would rendering it before the catalog has loaded.
  const videoCatalogModels = videoCatalog.filter((item) => item.provider === provider).map((item) => item.model);

  const userConfigs = userQuery.data?.configs ?? emptyConfigs;
  const officialConfigs = isSuperAdmin
    ? officialQuery.data?.configs ?? emptyConfigs
    : userQuery.data?.officialConfigs ?? emptyConfigs;
  const activeUserByPurpose = useMemo(
    () => configsByPurpose(userConfigs, (config) => config.isActive && config.isEnabled),
    [userConfigs]
  );

  const rows = useMemo(() => [...officialConfigs, ...userConfigs], [officialConfigs, userConfigs]);
  const providerFilters = useMemo(
    () =>
      Array.from(
        new Set(Object.values(providerOptions).flat().map((option) => option.value))
      ).filter(Boolean),
    []
  );

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((config) => {
      const checked = isDefaultConfig(config, activeUserByPurpose);
      if (sourceFilter !== "all" && config.source !== sourceFilter) {
        return false;
      }
      if (purposeFilter !== "all" && config.purpose !== purposeFilter) {
        return false;
      }
      if (providerFilter !== "all" && config.provider !== providerFilter) {
        return false;
      }
      if (defaultFilter === "default" && !checked) {
        return false;
      }
      if (defaultFilter === "not-default" && checked) {
        return false;
      }
      if (enabledFilter === "enabled" && !config.isEnabled) {
        return false;
      }
      if (enabledFilter === "disabled" && config.isEnabled) {
        return false;
      }
      if (!q) {
        return true;
      }
      return `${config.name} ${config.description}`.toLowerCase().includes(q);
    });
  }, [
    activeUserByPurpose,
    defaultFilter,
    enabledFilter,
    providerFilter,
    purposeFilter,
    rows,
    search,
    sourceFilter,
  ]);

  const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageRows = filteredRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const options = providerOptions[purpose];
  const isRelay = isRelayConnection(provider, connectionMode);
  const selectedProviderOption = providerOption(purpose, provider);
  const usesKnownModelList =
    ["edge", "system"].includes(provider) ||
    (provider === "qwen" &&
      (!baseUrl.trim() || baseUrl.trim() === "https://dashscope.aliyuncs.com/api/v1")) ||
    (provider === "doubao" &&
      (!baseUrl.trim() || baseUrl.trim() === "https://ark.cn-beijing.volces.com/api/v3"));
  const isMutating = (isSuperAdmin && officialQuery.isLoading) || userQuery.isLoading;

  const refreshConfigs = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.officialConfigs }),
      queryClient.invalidateQueries({ queryKey: queryKeys.userConfigs }),
    ]);
  };

  const resetForm = () => {
    const option = defaultProviderOption();
    setEditingConfig(null);
    setIsOfficial(false);
    setName("");
    setDescription("");
    setPurpose("script");
    setProvider(option.value);
    setConnectionMode("direct");
    setBaseUrl(option.baseUrl ?? "");
    setModelSeries(option.modelSeries);
    setApiKey("");
    setShowApiKey(false);
    setModelOptions([]);
    setIsEnabled(true);
    setIsDefault(false);
    setPricingMultiplier("1");
    setInputPricePerMillion("0");
    setOutputPricePerMillion("0");
    setCacheReadPricePerMillion("0");
    setCacheWritePricePerMillion("0");
    setUnitPrice("0");
    setImageMaxReferenceImages(4);
    setVideoCapabilities(defaultVideoCapabilities(option.value));
  };

  const openCreate = () => {
    resetForm();
    setFormOpen(true);
  };

  const openEdit = async (config: UserConfig) => {
    try {
      const secret = isSuperAdmin
        ? await getModelConfigSecretAction(config.id)
        : await getUserConfigSecretAction(config.id);
      setApiKey(secret.apiKey);
    } catch (error) {
      toast.add({
        title: resolveRequestError(error, t("admin.loadApiKeyFailed")),
        type: "error",
        priority: "high",
      });
      return;
    }
    setEditingConfig(config);
    setIsOfficial(config.source === "official");
    setName(config.name);
    setDescription(config.description);
    setPurpose(config.purpose);
    setProvider(config.provider);
    const mode = connectionModeFromConfig(config);
    setConnectionMode(mode);
    setBaseUrl(config.baseUrl || baseUrlForConnection(config.purpose, config.provider, mode));
    setModelSeries(config.modelSeries);
    setShowApiKey(false);
    setModelOptions([]);
    setIsEnabled(config.isEnabled);
    setIsDefault(isDefaultConfig(config, activeUserByPurpose));
    setPricingMultiplier(String(config.pricingMultiplier));
    setInputPricePerMillion(String(config.inputPricePerMillion));
    setOutputPricePerMillion(String(config.outputPricePerMillion));
    setCacheReadPricePerMillion(String(config.cacheReadPricePerMillion));
    setCacheWritePricePerMillion(String(config.cacheWritePricePerMillion));
    setUnitPrice(String(config.unitPrice));
    setImageMaxReferenceImages(config.imageMaxReferenceImages ?? 4);
    setVideoCapabilities(editableVideoCapabilities(config));
    setFormOpen(true);
  };

  const onPurposeChange = (nextPurpose: string | null) => {
    const value = (nextPurpose ?? "script") as ConfigPurpose;
    const option = providerOption(value, provider) ?? defaultProviderOption(value);
    const mode = option.value === "custom" ? "relay" : connectionMode;
    setPurpose(value);
    setProvider(option.value);
    setName(providerLabel(option.value, t));
    setConnectionMode(mode);
    setBaseUrl(baseUrlForConnection(value, option.value, mode));
    setModelSeries(option.modelSeries);
    setModelOptions([]);
    setUnitPrice("0");
    setImageMaxReferenceImages(4);
    setVideoCapabilities(defaultVideoCapabilities(option.value));
  };

  const onProviderChange = (nextProvider: string | null) => {
    const value = nextProvider ?? defaultProviderOption(purpose).value;
    const option = providerOption(purpose, value) ?? defaultProviderOption(purpose);
    const mode = value === "custom" ? "relay" : "direct";
    setProvider(value);
    setName(providerLabel(option.value, t));
    setConnectionMode(mode);
    setBaseUrl(baseUrlForConnection(purpose, value, mode));
    setModelSeries(option.modelSeries);
    setModelOptions([]);
    setVideoCapabilities(defaultVideoCapabilities(value));
    setImageMaxReferenceImages(4);
    if (["edge", "system"].includes(value)) setApiKey("");
  };

  const onConnectionModeChange = (value: string | null) => {
    const mode = provider === "custom" ? "relay" : (value as ConnectionMode | null) ?? "direct";
    setConnectionMode(mode);
    setBaseUrl(baseUrlForConnection(purpose, provider, mode));
    setModelOptions([]);
  };

  const discoverModelsMutation = useMutation({
    mutationFn: () => {
      if (!usesKnownModelList && !apiKey.trim()) {
        throw new Error(t("admin.enterApiKeyBeforeFetchModels"));
      }
      if (isRelay && !baseUrl.trim()) {
        throw new Error(t("admin.enterRelayBaseUrl"));
      }
      return discoverModelsAction({ provider, baseUrl: baseUrl.trim(), apiKey: apiKey.trim() });
    },
    onSuccess: ({ models }) => {
      setModelOptions(models);
      toast.add({ title: t("admin.modelsFetched", { count: models.length }), type: "success" });
    },
    onError: (error) =>
      toast.add({
        title: resolveRequestError(
          error,
          error instanceof Error ? error.message : t("admin.fetchModelsFailed")
        ),
        type: "error",
        priority: "high",
      }),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!modelSeries.trim()) {
        throw new Error(t("admin.enterModelSeries"));
      }
      if (isRelay && !baseUrl.trim()) {
        throw new Error(t("admin.enterRelayBaseUrl"));
      }
      if (isDefault && !isEnabled) {
        throw new Error(t("admin.disabledCannotBeDefault"));
      }
      const saveAsOfficial = isSuperAdmin && isOfficial;
      if (editingConfig?.source === "official" && !isSuperAdmin) {
        throw new Error(t("admin.noEditOfficialPermission"));
      }
      if (
        !["edge", "system"].includes(provider) &&
        !editingConfig &&
        !saveAsOfficial &&
        !apiKey.trim()
      ) {
        throw new Error(t("admin.userConfigNeedsApiKey"));
      }
      if (
        !["edge", "system"].includes(provider) &&
        saveAsOfficial &&
        isEnabled &&
        !apiKey.trim()
      ) {
        throw new Error(t("admin.officialEnabledNeedsApiKey"));
      }
      if (editingConfig && isDefaultConfig(editingConfig, activeUserByPurpose) && !isDefault) {
        throw new Error(t("admin.keepOneDefault"));
      }

      const payload = {
        name: name.trim(),
        description: description.trim(),
        purpose,
        provider,
        baseUrl: baseUrl.trim(),
        modelSeries: modelSeries.trim(),
        apiKey: apiKey.trim() || undefined,
        isActive: isDefault,
        isEnabled,
        pricingMultiplier,
        inputPricePerMillion,
        outputPricePerMillion,
        cacheReadPricePerMillion,
        cacheWritePricePerMillion,
        unitPrice:
          purpose === "image" || purpose === "video" || purpose === "audio" ? unitPrice : "0",
        unitName: defaultPricingUnit(purpose),
        imageMaxReferenceImages: purpose === "image" ? imageMaxReferenceImages : undefined,
        videoCapabilities: purpose === "video" ? videoCapabilities : undefined,
      };

      if (editingConfig) {
        if (isSuperAdmin) {
          await updateModelConfigAction(editingConfig.id, {
            ...payload,
            source: saveAsOfficial ? "official" : "user",
          });
        } else {
          await updateUserConfigAction(editingConfig.id, payload);
        }
        return;
      }
      if (saveAsOfficial) {
        await createOfficialConfigAction({ ...payload, apiKey: apiKey.trim() });
      } else {
        await createUserConfigAction({ ...payload, apiKey: apiKey.trim() });
      }
    },
    onSuccess: async () => {
      setFormOpen(false);
      resetForm();
      toast.add({ title: t("admin.saveConfigSuccess"), type: "success" });
      await refreshConfigs();
    },
    onError: (error) =>
      toast.add({
        title: resolveRequestError(
          error,
          error instanceof Error ? error.message : t("admin.saveConfigFailed")
        ),
        type: "error",
        priority: "high",
      }),
  });

  const defaultMutation = useMutation({
    mutationFn: async ({ config, checked }: { config: UserConfig; checked: boolean }) => {
      if (!checked) {
        throw new Error(t("admin.chooseOtherDefault"));
      }
      if (checked && !config.isEnabled) {
        throw new Error(t("admin.disabledCannotBeDefault"));
      }
      if (config.source === "official") {
        if (!isSuperAdmin) {
          await activateOfficialConfigAction(config.id);
          return;
        }
        await Promise.all(
          userConfigs
            .filter((item) => item.purpose === config.purpose && item.isActive)
            .map((item) => updateUserConfigAction(item.id, { isActive: false }))
        );
        await updateOfficialConfigAction(config.id, { isActive: checked });
      } else {
        await updateUserConfigAction(config.id, { isActive: checked });
      }
    },
    onSuccess: async () => {
      toast.add({ title: t("admin.defaultUpdated"), type: "success" });
      await refreshConfigs();
    },
    onError: (error) =>
      toast.add({
        title: resolveRequestError(
          error,
          error instanceof Error ? error.message : t("admin.updateDefaultFailed")
        ),
        type: "error",
        priority: "high",
      }),
  });

  const enabledMutation = useMutation({
    mutationFn: (config: UserConfig) => {
      if (config.isEnabled && isDefaultConfig(config, activeUserByPurpose)) {
        throw new Error(t("admin.defaultCannotDisable"));
      }
      if (config.source === "official" && !isSuperAdmin) {
        throw new Error(t("admin.noModifyOfficialPermission"));
      }
      return config.source === "official"
        ? updateOfficialConfigAction(config.id, { isEnabled: !config.isEnabled })
        : updateUserConfigAction(config.id, { isEnabled: !config.isEnabled });
    },
    onSuccess: async () => {
      toast.add({ title: t("admin.enabledUpdated"), type: "success" });
      await refreshConfigs();
    },
    onError: (error) =>
      toast.add({
        title: resolveRequestError(error, t("admin.updateEnabledFailed")),
        type: "error",
        priority: "high",
      }),
  });

  const deleteMutation = useMutation({
    mutationFn: (config: UserConfig) => {
      if (config.source === "official" && !isSuperAdmin) {
        throw new Error(t("admin.noDeleteOfficialPermission"));
      }
      return config.source === "official"
        ? deleteOfficialConfigAction(config.id)
        : deleteUserConfigAction(config.id);
    },
    onSuccess: async () => {
      setDeletingConfig(null);
      toast.add({ title: t("admin.configDeleted"), type: "success" });
      await refreshConfigs();
    },
    onError: (error) =>
      toast.add({
        title: resolveRequestError(error, t("admin.deleteConfigFailed")),
        type: "error",
        priority: "high",
      }),
  });

  const busy =
    saveMutation.isPending ||
    defaultMutation.isPending ||
    enabledMutation.isPending ||
    deleteMutation.isPending ||
    isMutating;
  const filtersActive =
    Boolean(search.trim()) ||
    purposeFilter !== "all" ||
    providerFilter !== "all" ||
    sourceFilter !== "all" ||
    defaultFilter !== "all" ||
    enabledFilter !== "all";

  return (
    <div className="min-w-0 space-y-4">
      {/* 顶部标题与新建按钮 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold tracking-tight text-foreground">
            {t("admin.configTitle")}
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t("admin.configDescription")}
          </p>
        </div>
        <Button
          onClick={openCreate}
          className="h-9 gap-1.5 rounded-xl font-semibold shadow-xs cursor-pointer"
        >
          <Plus className="size-4" />
          {t("settings.newConfig")}
        </Button>
      </div>

      {/* 筛选与搜索卡片 */}
      <div className="grid gap-2.5 rounded-2xl border border-border/70 bg-card/40 p-3.5 backdrop-blur-xl md:grid-cols-2 xl:grid-cols-[minmax(180px,1.2fr)_140px_140px_140px_130px_130px_auto]">
        <Input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder={t("admin.searchConfig")}
          className="h-9 text-xs"
        />
        <Select
          value={purposeFilter}
          onValueChange={(value) => {
            setPurposeFilter((value ?? "all") as "all" | ConfigPurpose);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-9 text-xs">
            <SelectValue>
              {purposeFilter === "all" ? t("admin.allPurposes") : purposeLabel[purposeFilter]}
            </SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            <SelectItem value="all" label={t("admin.allPurposes")} className="text-xs">
              {t("admin.allPurposes")}
            </SelectItem>
            {Object.entries(purposeLabel).map(([value, label]) => (
              <SelectItem key={value} value={value} label={label} className="text-xs">
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={providerFilter}
          onValueChange={(value) => {
            setProviderFilter(value ?? "all");
            setPage(1);
          }}
        >
          <SelectTrigger className="h-9 text-xs">
            <SelectValue>
              {providerFilter === "all"
                ? t("admin.allProviders")
                : providerLabel(providerFilter, t)}
            </SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            <SelectItem value="all" label={t("admin.allProviders")} className="text-xs">
              {t("admin.allProviders")}
            </SelectItem>
            {providerFilters.map((value) => (
              <SelectItem
                key={value}
                value={value}
                label={providerLabel(value, t)}
                className="text-xs"
              >
                {providerLabel(value, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={sourceFilter}
          onValueChange={(value) => {
            setSourceFilter((value ?? "all") as SourceFilter);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-9 text-xs">
            <SelectValue>
              {sourceFilter === "all"
                ? t("admin.allSources")
                : sourceFilter === "official"
                  ? t("settings.officialConfig")
                  : t("admin.userConfig")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            <SelectItem value="all" label={t("admin.allSources")} className="text-xs">
              {t("admin.allSources")}
            </SelectItem>
            <SelectItem value="official" label={t("settings.officialConfig")} className="text-xs">
              {t("settings.officialConfig")}
            </SelectItem>
            <SelectItem value="user" label={t("admin.userConfig")} className="text-xs">
              {t("admin.userConfig")}
            </SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={defaultFilter}
          onValueChange={(value) => {
            setDefaultFilter((value ?? "all") as DefaultFilter);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-9 text-xs">
            <SelectValue>
              {defaultFilter === "all"
                ? t("admin.allDefaults")
                : defaultFilter === "default"
                  ? t("admin.default")
                  : t("admin.notDefault")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            <SelectItem value="all" label={t("admin.allDefaults")} className="text-xs">
              {t("admin.allDefaults")}
            </SelectItem>
            <SelectItem value="default" label={t("admin.default")} className="text-xs">
              {t("admin.default")}
            </SelectItem>
            <SelectItem value="not-default" label={t("admin.notDefault")} className="text-xs">
              {t("admin.notDefault")}
            </SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={enabledFilter}
          onValueChange={(value) => {
            setEnabledFilter((value ?? "all") as EnabledFilter);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-9 text-xs">
            <SelectValue>
              {enabledFilter === "all"
                ? t("admin.allStatuses")
                : enabledFilter === "enabled"
                  ? t("settings.enable")
                  : t("settings.disable")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            <SelectItem value="all" label={t("admin.allStatuses")} className="text-xs">
              {t("admin.allStatuses")}
            </SelectItem>
            <SelectItem value="enabled" label={t("settings.enable")} className="text-xs">
              {t("settings.enable")}
            </SelectItem>
            <SelectItem value="disabled" label={t("settings.disable")} className="text-xs">
              {t("settings.disable")}
            </SelectItem>
          </SelectContent>
        </Select>

        {filtersActive ? (
          <Button
            variant="outline"
            size="sm"
            className="h-9 gap-1 text-xs cursor-pointer"
            onClick={() => {
              setSearch("");
              setPurposeFilter("all");
              setProviderFilter("all");
              setSourceFilter("all");
              setDefaultFilter("all");
              setEnabledFilter("all");
              setPage(1);
            }}
          >
            <RotateCcw className="size-3.5" />
            {t("common.clearFilters")}
          </Button>
        ) : null}
      </div>

      {/* 配置数据表格 */}
      <div className="overflow-x-auto rounded-2xl border border-border/70 bg-card/30 backdrop-blur-sm shadow-xs">
        <table className="w-full min-w-[1120px] text-sm">
          <thead className="border-b border-border/70 bg-muted/40 text-xs font-semibold text-muted-foreground">
            <tr>
              <th className="px-4 py-3 text-left">{t("settings.name")}</th>
              <th className="px-3 py-3 text-left">{t("settings.purpose")}</th>
              <th className="px-3 py-3 text-left">{t("settings.provider")}</th>
              <th className="px-3 py-3 text-left">{t("admin.tableModel")}</th>
              <th className="px-3 py-3 text-left">{t("admin.status")}</th>
              <th className="px-3 py-3 text-center">{t("admin.tableDefault")}</th>
              <th className="px-3 py-3 text-left">{t("admin.tableUpdatedAt")}</th>
              <th className="px-4 py-3 text-center">{t("admin.tableActions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {pageRows.map((config) => {
              const checked = isDefaultConfig(config, activeUserByPurpose);
              const canManageConfig = config.source === "user" || isSuperAdmin;
              return (
                <tr
                  key={rowKey(config)}
                  className="transition-colors hover:bg-muted/30"
                >
                  <td className="max-w-64 px-4 py-3">
                    <p className="truncate font-semibold text-foreground">
                      {configTitle(config, purposeLabel, t)}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] text-muted-foreground font-mono">
                      {config.description || config.baseUrl || "—"}
                    </p>
                  </td>
                  <td className="px-3 py-3">
                    <Badge variant="secondary" className="text-[11px] font-medium">
                      {purposeLabel[config.purpose]}
                    </Badge>
                  </td>
                  <td className="px-3 py-3">
                    <span className="font-medium text-xs text-foreground">
                      {providerLabel(config.provider, t)}
                    </span>
                  </td>
                  <td className="max-w-44 truncate px-3 py-3 font-mono text-xs text-foreground/90">
                    {config.modelSeries}
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge
                        variant={config.source === "official" ? "default" : "secondary"}
                        className="text-[10px]"
                      >
                        {config.source === "official"
                          ? t("config.source.official")
                          : t("config.source.user")}
                      </Badge>
                      <Badge
                        variant={config.isEnabled ? "outline" : "destructive"}
                        className="text-[10px]"
                      >
                        {config.isEnabled ? t("settings.enable") : t("settings.disable")}
                      </Badge>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-center">
                    <Switch
                      checked={checked}
                      disabled={busy || !config.isEnabled}
                      onCheckedChange={(next) => defaultMutation.mutate({ config, checked: next })}
                      className="mx-auto cursor-pointer"
                    />
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                    {formatDateTime(config.updatedAt)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center gap-1">
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        onClick={() => setViewingConfig(config)}
                        title={t("admin.view")}
                        className="cursor-pointer text-muted-foreground hover:text-foreground"
                      >
                        <Eye className="size-3.5" />
                      </Button>
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        disabled={!canManageConfig}
                        onClick={() => void openEdit(config)}
                        title={t("common.edit")}
                        className="cursor-pointer text-muted-foreground hover:text-foreground"
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Switch
                        checked={config.isEnabled}
                        disabled={busy || !canManageConfig}
                        onCheckedChange={() => enabledMutation.mutate(config)}
                        className="mx-1 self-center scale-90 cursor-pointer"
                      />
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        disabled={!canManageConfig}
                        onClick={() => setDeletingConfig(config)}
                        title={t("common.delete")}
                        className="cursor-pointer text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!busy && pageRows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-xs text-muted-foreground">
                  {t("admin.noMatchingConfigs")}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {/* 分页控制 */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>
          {t("admin.pagination", { total: filteredRows.length, page: currentPage, pageCount })}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs cursor-pointer"
            disabled={currentPage <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            {t("common.previous")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs cursor-pointer"
            disabled={currentPage >= pageCount}
            onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
          >
            {t("common.next")}
          </Button>
        </div>
      </div>

      {/* 模型配置 新建 / 编辑 Dialog（全量卡片化重构） */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh] flex flex-col p-0 overflow-hidden gap-0">
          <DialogHeader className="p-5 border-b border-border/70">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <Cpu className="size-4" />
                </div>
                <div>
                  <DialogTitle className="text-base font-bold">
                    {editingConfig ? t("settings.editConfig") : t("settings.newConfig")}
                  </DialogTitle>
                  <DialogDescription className="text-xs mt-0.5">
                    {t("admin.emptyApiKeyKeepsCurrent")}
                  </DialogDescription>
                </div>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground bg-muted/40 px-2 py-1 rounded-md border border-border/50">
                <span className="font-bold text-destructive mr-0.5">*</span>为必填字段
              </span>
            </div>
          </DialogHeader>

          {/* 表单滚动主体区 */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4 chat-message-list-scrollbar">
            {/* 官方配置标识开关（超管可见） */}
            {isSuperAdmin ? (
              <div className="flex items-center justify-between rounded-xl border border-primary/20 bg-primary/5 p-3.5">
                <div className="space-y-0.5">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Sparkles className="size-3.5 text-primary" />
                    {t("admin.asOfficialConfig")}
                  </span>
                  <p className="text-[11px] text-muted-foreground">
                    作为全站官方共享模型，所有用户可直接选用
                  </p>
                </div>
                <Switch
                  checked={isOfficial}
                  onCheckedChange={setIsOfficial}
                  className="cursor-pointer"
                />
              </div>
            ) : null}

            {/* 模块 1: 基础属性与服务商 */}
            <div className="space-y-3 rounded-2xl border border-border/70 bg-card/40 p-4">
              <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                <Layers className="size-3.5 text-primary" />
                <span>基础信息与服务商</span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="adminConfigPurpose" className="text-xs font-semibold text-foreground/90">
                    {t("settings.purpose")}
                    <RequiredAsterisk />
                  </Label>
                  <Select value={purpose} onValueChange={onPurposeChange}>
                    <SelectTrigger id="adminConfigPurpose" className="h-9 w-full text-xs">
                      <SelectValue>{purposeLabel[purpose]}</SelectValue>
                    </SelectTrigger>
                    <SelectContent alignItemWithTrigger={false}>
                      {Object.entries(purposeLabel).map(([value, label]) => (
                        <SelectItem key={value} value={value} label={label} className="text-xs">
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="adminConfigProvider" className="text-xs font-semibold text-foreground/90">
                    {t("settings.provider")}
                    <RequiredAsterisk />
                  </Label>
                  <Select value={provider} onValueChange={onProviderChange}>
                    <SelectTrigger id="adminConfigProvider" className="h-9 w-full text-xs">
                      <SelectValue>{providerLabel(provider, t)}</SelectValue>
                    </SelectTrigger>
                    <SelectContent alignItemWithTrigger={false}>
                      {options.map((option) => (
                        <SelectItem
                          key={option.value}
                          value={option.value}
                          label={providerLabel(option.value, t)}
                          className="text-xs"
                        >
                          {providerLabel(option.value, t)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="adminConfigName" className="text-xs font-semibold text-foreground/90">
                    {t("settings.name")}
                  </Label>
                  <Input
                    id="adminConfigName"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="例如：通义千问 2.5 旗舰"
                    className="h-9 text-xs"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="adminConfigConnection" className="text-xs font-semibold text-foreground/90">
                    {t("settings.connectionMode")}
                    <RequiredAsterisk />
                  </Label>
                  <Select
                    value={isRelay ? "relay" : "direct"}
                    onValueChange={onConnectionModeChange}
                  >
                    <SelectTrigger id="adminConfigConnection" className="h-9 w-full text-xs">
                      <SelectValue>
                        {isRelay ? t("admin.connectionRelay") : t("settings.officialDirect")}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent alignItemWithTrigger={false}>
                      {provider !== "custom" ? (
                        <SelectItem value="direct" label={t("settings.officialDirect")} className="text-xs">
                          {t("settings.officialDirect")}
                        </SelectItem>
                      ) : null}
                      <SelectItem value="relay" label={t("admin.connectionRelay")} className="text-xs">
                        {t("admin.connectionRelay")}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            {/* 模块 2: 连接凭证与模型系列 */}
            <div className="space-y-3 rounded-2xl border border-border/70 bg-card/40 p-4">
              <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                <Globe className="size-3.5 text-primary" />
                <span>连接凭据与模型系列</span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="adminConfigBaseUrl" className="text-xs font-semibold text-foreground/90">
                    Base URL
                    {isRelay || provider === "custom" ? <RequiredAsterisk /> : null}
                  </Label>
                  <Input
                    id="adminConfigBaseUrl"
                    value={baseUrl}
                    onChange={(event) => {
                      setBaseUrl(event.target.value);
                      setModelOptions([]);
                    }}
                    placeholder="https://api.example.com/v1"
                    className="h-9 text-xs font-mono"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="adminConfigKey" className="text-xs font-semibold text-foreground/90">
                    API Key
                    {!editingConfig && !["edge", "system"].includes(provider) ? (
                      <RequiredAsterisk />
                    ) : null}
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      id="adminConfigKey"
                      type={showApiKey ? "text" : "password"}
                      value={apiKey}
                      autoComplete="off"
                      onChange={(event) => {
                        setApiKey(event.target.value);
                        setModelOptions([]);
                      }}
                      placeholder={
                        editingConfig ? t("admin.apiKeyKeepCurrent") : t("admin.apiKeyInput")
                      }
                      disabled={["edge", "system"].includes(provider)}
                      className="h-9 text-xs font-mono"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      aria-label={showApiKey ? t("admin.hideApiKey") : t("admin.showApiKey")}
                      title={showApiKey ? t("admin.hideApiKey") : t("admin.showApiKey")}
                      disabled={["edge", "system"].includes(provider)}
                      onClick={() => setShowApiKey((value) => !value)}
                      className="h-9 w-9 shrink-0 cursor-pointer"
                    >
                      {showApiKey ? (
                        <EyeOff className="size-4" />
                      ) : (
                        <Eye className="size-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </div>

              {/* 模型系列 + 发现模型 */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="adminConfigModel" className="text-xs font-semibold text-foreground/90">
                    {t("settings.modelSeries")}
                    <RequiredAsterisk />
                  </Label>
                  {purpose === "audio" ? null : (
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      onClick={() => discoverModelsMutation.mutate()}
                      disabled={discoverModelsMutation.isPending}
                      className="h-7 gap-1 text-[11px] cursor-pointer"
                    >
                      <RefreshCw
                        className={cn(
                          "size-3 text-primary",
                          discoverModelsMutation.isPending && "animate-spin"
                        )}
                      />
                      {discoverModelsMutation.isPending
                        ? t("admin.fetchingModels")
                        : t("admin.fetchModels")}
                    </Button>
                  )}
                </div>
                <ModelSeriesCombobox
                  id="adminConfigModel"
                  value={modelSeries}
                  options={purpose === "video" ? Array.from(new Set([...videoCatalogModels, ...modelOptions])) : modelOptions}
                  onChange={(value) => {
                    setModelSeries(value);
                    if (purpose === "video")
                      setVideoCapabilities(
                        videoCatalog.find((item) => item.model === value)?.capabilities
                          ?? defaultVideoCapabilities(provider, value),
                      );
                  }}
                  placeholder={selectedProviderOption?.modelPlaceholder}
                  selectLabel={t("admin.selectModelSeries")}
                  emptyLabel={t("admin.noMatchingModels")}
                />
              </div>

              {/* 描述备注 */}
              <div className="space-y-1.5 pt-1">
                <Label htmlFor="adminConfigDescription" className="text-xs font-semibold text-foreground/90">
                  {t("settings.descriptionLabel")}
                </Label>
                <Textarea
                  id="adminConfigDescription"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="请输入该模型配置的用途说明或特点备注..."
                  className="min-h-20 text-xs resize-none rounded-xl"
                />
              </div>
            </div>

            {/* 模块 3: 专业能力与媒体规格 (图片/视频专用) */}
            {purpose === "image" ? (
              <div className="space-y-3 rounded-2xl border border-border/70 bg-card/40 p-4">
                <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                  <ImageIcon className="size-3.5 text-primary" />
                  <span>图像模型规格</span>
                </div>
                <NumberInput
                  id="imageMaxReferenceImages"
                  label={t("admin.maxReferenceImages")}
                  value={imageMaxReferenceImages}
                  min={0}
                  max={10}
                  onChange={setImageMaxReferenceImages}
                />
              </div>
            ) : null}

            {purpose === "video" ? (
              <div className="space-y-4 rounded-2xl border border-border/80 bg-card/40 p-4">
                <div className="flex items-center justify-between border-b border-border/60 pb-2.5">
                  <div className="flex items-center gap-1.5">
                    <Video className="size-4 text-primary" />
                    <div>
                      <p className="text-xs font-bold text-foreground">
                        {t("admin.videoCapabilities")}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        配置该视频模型支持的分辨率、比例、时长与参考素材限制
                      </p>
                    </div>
                  </div>
                  <Badge variant="outline" className="text-[10px]">
                    Video Specs
                  </Badge>
                </div>

                {/* 分组 1: 输出格式与规格 */}
                <div className="space-y-2.5">
                  <p className="text-[11px] font-semibold text-muted-foreground">
                    🎞️ 输出格式与规格
                  </p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <CapabilitySelect
                      label={t("admin.supportsVideoQuality")}
                      values={videoCapabilities.qualities}
                      options={videoQualityOptions}
                      onChange={(qualities) =>
                        setVideoCapabilities((current) => ({ ...current, qualities }))
                      }
                    />
                    <CapabilitySelect
                      label={t("admin.supportsAspectRatio")}
                      values={videoCapabilities.aspectRatios}
                      options={videoAspectRatioOptions}
                      format={(value) =>
                        value === "adaptive" ? t("admin.aspectRatioAdaptive") : value
                      }
                      onChange={(aspectRatios) =>
                        setVideoCapabilities((current) => ({ ...current, aspectRatios }))
                      }
                    />
                  </div>
                </div>

                {/* 分组 2: 时长控制与智能扩写 */}
                <div className="space-y-3 border-t border-border/50 pt-3">
                  <p className="text-[11px] font-semibold text-muted-foreground">
                    ⏱️ 时长限制与生成增强
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <NumberInput
                      id="videoMinDuration"
                      label={t("admin.videoMinDuration")}
                      value={videoCapabilities.minDuration}
                      min={1}
                      max={60}
                      onChange={(minDuration) =>
                        setVideoCapabilities((current) => ({ ...current, minDuration }))
                      }
                    />
                    <NumberInput
                      id="videoMaxDuration"
                      label={t("admin.videoMaxDuration")}
                      value={videoCapabilities.maxDuration}
                      min={1}
                      max={120}
                      onChange={(maxDuration) =>
                        setVideoCapabilities((current) => ({ ...current, maxDuration }))
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between rounded-xl border border-border/60 bg-muted/30 p-3">
                    <div>
                      <p className="text-xs font-semibold text-foreground">
                        {t("admin.supportsPromptExtend")}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        允许模型根据简短提示词自动扩写丰富运镜与动作细节
                      </p>
                    </div>
                    <Switch
                      checked={videoCapabilities.promptExtend}
                      onCheckedChange={(promptExtend) =>
                        setVideoCapabilities((current) => ({ ...current, promptExtend }))
                      }
                      className="cursor-pointer"
                    />
                  </div>
                </div>

                {/* 分组 3: 多模态参考素材 (图片/视频/音频) */}
                <div className="space-y-3 border-t border-border/50 pt-3">
                  <p className="text-[11px] font-semibold text-muted-foreground">
                    🖼️ 多模态参考素材 (图/视/音生视频)
                  </p>

                  {/* 3.1 参考图片 */}
                  <div className="rounded-xl border border-border/70 bg-card/60 p-3 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="flex size-6 items-center justify-center rounded-lg bg-primary/10 text-primary text-xs font-bold">
                          图
                        </span>
                        <div>
                          <p className="text-xs font-semibold text-foreground">
                            {t("admin.supportsReferenceImages")}
                          </p>
                          <p className="text-[10px] text-muted-foreground">
                            图片仅作为附加参考素材，不使用首尾帧语义
                          </p>
                        </div>
                      </div>
                      <Switch
                        checked={videoCapabilities.referenceImages}
                        onCheckedChange={(referenceImages) =>
                          setVideoCapabilities((current) => ({
                            ...current,
                            referenceImages,
                            maxReferenceImages: referenceImages
                              ? Math.max(1, current.maxReferenceImages)
                              : 0,
                            referenceImagesRequired:
                              referenceImages && current.referenceImagesRequired,
                          }))
                        }
                        className="cursor-pointer"
                      />
                    </div>

                    {videoCapabilities.referenceImages ? (
                      <div className="grid gap-3 sm:grid-cols-2 pt-1 border-t border-border/40">
                        <NumberInput
                          id="videoMaxReferenceImages"
                          label={t("admin.maxReferenceImages")}
                          value={videoCapabilities.maxReferenceImages}
                          min={1}
                          onChange={(maxReferenceImages) =>
                            setVideoCapabilities((current) => ({
                              ...current,
                              maxReferenceImages,
                              referenceImages: maxReferenceImages > 0,
                              referenceImagesRequired:
                                maxReferenceImages > 0 && current.referenceImagesRequired,
                            }))
                          }
                        />
                        <div className="flex items-center justify-between rounded-lg bg-muted/40 p-2.5 sm:self-end">
                          <span className="text-xs font-medium">
                            {t("admin.referenceImagesRequired")}
                          </span>
                          <Switch
                            checked={videoCapabilities.referenceImagesRequired}
                            disabled={videoCapabilities.maxReferenceImages === 0}
                            onCheckedChange={(referenceImagesRequired) =>
                              setVideoCapabilities((current) => ({
                                ...current,
                                referenceImagesRequired,
                              }))
                            }
                            className="cursor-pointer"
                          />
                        </div>
                      </div>
                    ) : null}
                    <div className="grid gap-2 border-t border-border/40 pt-2 sm:grid-cols-2">
                      {(["supportsFirstFrame", "supportsLastFrame"] as const).map((key) => (
                        <div key={key} className="flex items-center justify-between rounded-lg bg-muted/40 p-2.5">
                          <span className="text-xs font-medium">{key === "supportsFirstFrame" ? "支持首帧" : "支持尾帧"}</span>
                          <Switch checked={Boolean(videoCapabilities[key])} onCheckedChange={(checked) => setVideoCapabilities((current) => ({ ...current, [key]: checked }))} />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 3.2 参考视频 */}
                  <div className="rounded-xl border border-border/70 bg-card/60 p-3 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="flex size-6 items-center justify-center rounded-lg bg-blue-500/10 text-blue-400 text-xs font-bold">
                          视
                        </span>
                        <div>
                          <p className="text-xs font-semibold text-foreground">
                            {t("admin.supportsReferenceVideo")}
                          </p>
                          <p className="text-[10px] text-muted-foreground">
                            支持视频续写、视频编辑与风格重绘
                          </p>
                        </div>
                      </div>
                      <Switch
                        checked={videoCapabilities.referenceVideo}
                        onCheckedChange={(referenceVideo) =>
                          setVideoCapabilities((current) => ({
                            ...current,
                            referenceVideo,
                            maxReferenceVideos: referenceVideo
                              ? Math.max(1, current.maxReferenceVideos)
                              : 0,
                            referenceVideosRequired:
                              referenceVideo && current.referenceVideosRequired,
                          }))
                        }
                        className="cursor-pointer"
                      />
                    </div>

                    {videoCapabilities.referenceVideo ? (
                      <div className="grid gap-3 sm:grid-cols-2 pt-1 border-t border-border/40">
                        <NumberInput
                          id="videoMaxReferenceVideos"
                          label={t("admin.maxReferenceVideos")}
                          value={videoCapabilities.maxReferenceVideos}
                          min={1}
                          max={10}
                          onChange={(maxReferenceVideos) =>
                            setVideoCapabilities((current) => ({
                              ...current,
                              maxReferenceVideos,
                              referenceVideo: maxReferenceVideos > 0,
                            }))
                          }
                        />
                        <div className="flex items-center justify-between rounded-lg bg-muted/40 p-2.5 sm:self-end">
                          <span className="text-xs font-medium">
                            {t("admin.referenceVideosRequired")}
                          </span>
                          <Switch
                            checked={videoCapabilities.referenceVideosRequired}
                            onCheckedChange={(referenceVideosRequired) =>
                              setVideoCapabilities((current) => ({
                                ...current,
                                referenceVideosRequired,
                              }))
                            }
                            className="cursor-pointer"
                          />
                        </div>
                      </div>
                    ) : null}
                  </div>

                  {/* 3.3 参考音频 */}
                  <div className="rounded-xl border border-border/70 bg-card/60 p-3 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="flex size-6 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 text-xs font-bold">
                          音
                        </span>
                        <div>
                          <p className="text-xs font-semibold text-foreground">
                            {t("admin.supportsReferenceAudio")}
                          </p>
                          <p className="text-[10px] text-muted-foreground">
                            支持音频驱动配音对口型（Lip-sync）生成
                          </p>
                        </div>
                      </div>
                      <Switch
                        checked={videoCapabilities.referenceAudio}
                        onCheckedChange={(referenceAudio) =>
                          setVideoCapabilities((current) => ({
                            ...current,
                            referenceAudio,
                            maxReferenceAudios: referenceAudio
                              ? Math.max(1, current.maxReferenceAudios)
                              : 0,
                            referenceAudiosRequired:
                              referenceAudio && current.referenceAudiosRequired,
                          }))
                        }
                        className="cursor-pointer"
                      />
                    </div>

                    {videoCapabilities.referenceAudio ? (
                      <div className="grid gap-3 sm:grid-cols-2 pt-1 border-t border-border/40">
                        <NumberInput
                          id="videoMaxReferenceAudios"
                          label={t("admin.maxReferenceAudios")}
                          value={videoCapabilities.maxReferenceAudios}
                          min={1}
                          max={10}
                          onChange={(maxReferenceAudios) =>
                            setVideoCapabilities((current) => ({
                              ...current,
                              maxReferenceAudios,
                              referenceAudio: maxReferenceAudios > 0,
                            }))
                          }
                        />
                        <div className="flex items-center justify-between rounded-lg bg-muted/40 p-2.5 sm:self-end">
                          <span className="text-xs font-medium">
                            {t("admin.referenceAudiosRequired")}
                          </span>
                          <Switch
                            checked={videoCapabilities.referenceAudiosRequired}
                            onCheckedChange={(referenceAudiosRequired) =>
                              setVideoCapabilities((current) => ({
                                ...current,
                                referenceAudiosRequired,
                              }))
                            }
                            className="cursor-pointer"
                          />
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}

            {/* 模块 4: 计费与价格设定 */}
            <div className="space-y-3 rounded-2xl border border-border/70 bg-card/40 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                  <Coins className="size-3.5 text-primary" />
                  <span>{t("admin.pricingTitle")}</span>
                </div>
                <span className="text-[11px] text-muted-foreground">{t("admin.pricingHint")}</span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <PricingInput
                  id="pricingMultiplier"
                  label={t("admin.pricingMultiplier")}
                  value={pricingMultiplier}
                  onChange={setPricingMultiplier}
                  required
                />
                {purpose === "image" || purpose === "video" || purpose === "audio" ? (
                  <PricingInput
                    id="unitPrice"
                    label={t(
                      purpose === "image"
                        ? "admin.imageUnitPrice"
                        : purpose === "audio"
                          ? "admin.audioUnitPrice"
                          : "admin.videoUnitPrice"
                    )}
                    value={unitPrice}
                    onChange={setUnitPrice}
                    required
                  />
                ) : (
                  <>
                    <PricingInput
                      id="inputPrice"
                      label={t("admin.inputPrice")}
                      value={inputPricePerMillion}
                      onChange={setInputPricePerMillion}
                      required
                    />
                    <PricingInput
                      id="outputPrice"
                      label={t("admin.outputPrice")}
                      value={outputPricePerMillion}
                      onChange={setOutputPricePerMillion}
                      required
                    />
                    <PricingInput
                      id="cacheReadPrice"
                      label={t("admin.cacheReadPrice")}
                      value={cacheReadPricePerMillion}
                      onChange={setCacheReadPricePerMillion}
                    />
                    <PricingInput
                      id="cacheWritePrice"
                      label={t("admin.cacheWritePrice")}
                      value={cacheWritePricePerMillion}
                      onChange={setCacheWritePricePerMillion}
                    />
                  </>
                )}
              </div>
            </div>

            {/* 模块 5: 状态与生效 */}
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex items-center justify-between rounded-xl border border-border/70 bg-card/40 p-3.5 text-xs font-medium cursor-pointer transition-colors hover:bg-card/60">
                <div className="space-y-0.5">
                  <span className="text-foreground font-semibold">{t("admin.enabledStatus")}</span>
                  <p className="text-[11px] text-muted-foreground">控制此模型是否对调用开放</p>
                </div>
                <Switch
                  checked={isEnabled}
                  onCheckedChange={setIsEnabled}
                  className="cursor-pointer"
                />
              </label>
              <label className="flex items-center justify-between rounded-xl border border-border/70 bg-card/40 p-3.5 text-xs font-medium cursor-pointer transition-colors hover:bg-card/60">
                <div className="space-y-0.5">
                  <span className="text-foreground font-semibold">{t("admin.setDefault")}</span>
                  <p className="text-[11px] text-muted-foreground">设为对应用途的默认优先模型</p>
                </div>
                <Switch
                  checked={isDefault}
                  onCheckedChange={setIsDefault}
                  className="cursor-pointer"
                />
              </label>
            </div>
          </div>

          {/* 弹窗底部操作按钮 */}
          <DialogFooter className="m-0 p-4 border-t border-border/70 bg-muted/20 sm:gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFormOpen(false)}
              className="h-9 gap-1 text-xs cursor-pointer"
            >
              <X className="size-3.5" />
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="h-9 gap-1.5 text-xs font-bold cursor-pointer"
            >
              {saveMutation.isPending ? (
                <RefreshCw className="size-3.5 animate-spin" />
              ) : (
                <Check className="size-3.5" />
              )}
              {saveMutation.isPending ? t("settings.saving") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 模型详情查看 Dialog */}
      <Dialog
        open={Boolean(viewingConfig)}
        onOpenChange={(open) => !open && setViewingConfig(null)}
      >
        <DialogContent className="sm:max-w-lg p-0 overflow-hidden">
          <DialogHeader className="p-5 border-b border-border/70">
            <div className="flex items-center justify-between gap-2">
              <DialogTitle className="text-base font-bold flex items-center gap-2">
                <Cpu className="size-4 text-primary" />
                {viewingConfig ? configTitle(viewingConfig, purposeLabel, t) : t("admin.configDetails")}
              </DialogTitle>
              {viewingConfig ? (
                <Badge
                  variant={viewingConfig.source === "official" ? "default" : "secondary"}
                  className="text-[10px]"
                >
                  {viewingConfig.source === "official"
                    ? t("settings.officialConfig")
                    : t("admin.userConfig")}
                </Badge>
              ) : null}
            </div>
            <DialogDescription className="text-xs mt-1">
              {viewingConfig?.description || t("common.noDescription")}
            </DialogDescription>
          </DialogHeader>

          {viewingConfig ? (
            <div className="p-5 space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-2.5">
                <div className="rounded-xl border border-border/60 bg-muted/20 p-2.5">
                  <span className="text-[11px] text-muted-foreground block">{t("settings.purpose")}</span>
                  <span className="font-semibold text-foreground mt-0.5 block">
                    {purposeLabel[viewingConfig.purpose]}
                  </span>
                </div>
                <div className="rounded-xl border border-border/60 bg-muted/20 p-2.5">
                  <span className="text-[11px] text-muted-foreground block">{t("settings.provider")}</span>
                  <span className="font-semibold text-foreground mt-0.5 block">
                    {providerLabel(viewingConfig.provider, t)}
                  </span>
                </div>
                <div className="rounded-xl border border-border/60 bg-muted/20 p-2.5">
                  <span className="text-[11px] text-muted-foreground block">{t("admin.tableModel")}</span>
                  <span className="font-mono font-semibold text-foreground mt-0.5 block truncate">
                    {viewingConfig.modelSeries}
                  </span>
                </div>
                <div className="rounded-xl border border-border/60 bg-muted/20 p-2.5">
                  <span className="text-[11px] text-muted-foreground block">{t("admin.status")}</span>
                  <span className="font-semibold text-foreground mt-0.5 block">
                    {viewingConfig.isEnabled ? t("settings.enable") : t("settings.disable")}
                  </span>
                </div>
              </div>

              <div className="rounded-xl border border-border/60 bg-muted/20 p-2.5">
                <span className="text-[11px] text-muted-foreground block">Base URL</span>
                <span className="font-mono text-xs text-foreground mt-0.5 block break-all">
                  {viewingConfig.baseUrl || "—"}
                </span>
              </div>

              <div className="rounded-xl border border-primary/20 bg-primary/5 p-3 space-y-1">
                <span className="text-[11px] font-semibold text-primary block">计费策略</span>
                <p className="text-xs text-foreground font-medium">
                  {t("admin.pricingMultiplier")}: {viewingConfig.pricingMultiplier}x ·{" "}
                  {viewingConfig.purpose === "image" ||
                  viewingConfig.purpose === "video" ||
                  viewingConfig.purpose === "audio"
                    ? `${t(
                        viewingConfig.purpose === "image"
                          ? "admin.imageUnitPrice"
                          : viewingConfig.purpose === "audio"
                            ? "admin.audioUnitPrice"
                            : "admin.videoUnitPrice"
                      )}: $${viewingConfig.unitPrice}`
                    : `${t("admin.inputPrice")}: $${viewingConfig.inputPricePerMillion} · ${t("admin.outputPrice")}: $${viewingConfig.outputPricePerMillion}`}
                </p>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* 删除配置确认 Dialog */}
      <Dialog
        open={Boolean(deletingConfig)}
        onOpenChange={(open) => {
          if (!open && !deleteMutation.isPending) setDeletingConfig(null);
        }}
      >
        <DialogContent className="sm:max-w-md p-0 overflow-hidden">
          <DialogHeader className="p-5 border-b border-border/70">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
                <AlertTriangle className="size-5" />
              </div>
              <div>
                <DialogTitle className="text-base font-bold">
                  {t("common.delete")}
                </DialogTitle>
                <DialogDescription className="text-xs mt-0.5">
                  {deletingConfig
                    ? t("admin.confirmDeleteConfig", {
                        name: configTitle(deletingConfig, purposeLabel, t),
                      })
                    : ""}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <DialogFooter className="m-0 p-4 border-t border-border/70 bg-muted/20 sm:gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeletingConfig(null)}
              disabled={deleteMutation.isPending}
              className="h-9 text-xs cursor-pointer"
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => deletingConfig && deleteMutation.mutate(deletingConfig)}
              disabled={!deletingConfig || deleteMutation.isPending}
              className="h-9 gap-1.5 text-xs font-bold cursor-pointer"
            >
              <Trash2 className="size-3.5" />
              {deleteMutation.isPending ? t("common.loading") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RequiredAsterisk() {
  return (
    <span className="ml-1 font-bold text-destructive" title="必填项">
      *
    </span>
  );
}

function PricingInput({
  id,
  label,
  value,
  onChange,
  required = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-semibold text-foreground/90">
        {label}
        {required ? <RequiredAsterisk /> : null}
      </Label>
      <Input
        id={id}
        type="number"
        min="0"
        step="any"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 text-xs font-mono"
      />
    </div>
  );
}

function CapabilitySelect<T extends string | number>({
  label,
  values,
  options,
  onChange,
  format = String,
}: {
  label: string;
  values: T[];
  options: T[];
  onChange: (values: T[]) => void;
  format?: (value: T) => string;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-semibold text-foreground/90">{label}</Label>
      <Select
        multiple
        value={values}
        onValueChange={(value) => onChange((value ?? []) as T[])}
      >
        <SelectTrigger className="h-9 w-full text-xs">
          <SelectValue placeholder="请选择支持项">
            {values.length ? values.map(format).join(", ") : "未选择"}
          </SelectValue>
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false} className="max-h-60">
          {options.map((option) => (
            <SelectItem key={option} value={option} label={format(option)} className="text-xs">
              {format(option)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function NumberInput({
  id,
  label,
  value,
  onChange,
  min = 1,
  max,
  required = false,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  required?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-semibold text-foreground/90">
        {label}
        {required ? <RequiredAsterisk /> : null}
      </Label>
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        step="1"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-9 text-xs font-mono"
      />
    </div>
  );
}
