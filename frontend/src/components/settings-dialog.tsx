"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Power, Star, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import {
  activateOfficialConfigAction,
  createUserConfigAction,
  deleteUserConfigAction,
  listUserConfigsAction,
  updateUserConfigAction,
  validateUserConfigAction,
} from "@/actions/settings-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { resolveRequestError } from "@/lib/http/errors";
import {
  baseUrlForConnection,
  connectionModeFromConfig,
  configsByPurpose,
  type ConnectionMode,
  defaultProviderOption,
  isRelayConnection,
  providerLabelMap,
  providerOption,
  providerOptions,
} from "@/lib/model-providers";
import { cn } from "@/lib/utils";
import type { ConfigPurpose, CreateUserConfigInput, UpdateUserConfigInput, UserConfig } from "@/types/auth";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}

function connectionModeLabel(isRelay: boolean, direct: string, relay: string) {
  return isRelay ? relay : direct;
}

function displayConfigName(
  config: UserConfig | undefined,
  unconfiguredLabel: string,
  officialLabel: string,
  customLabel: string
) {
  if (!config) {
    return unconfiguredLabel;
  }
  const sourceLabel = config.source === "official" ? officialLabel : customLabel;

  if (config.name?.trim()) {
    return `${sourceLabel} · ${config.name} · ${config.modelSeries}`;
  }

  const providerLabel = providerLabelMap[config.provider] ?? config.provider;
  return `${sourceLabel} · ${providerLabel} · ${config.modelSeries}`;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();

  const [editingConfigId, setEditingConfigId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [purpose, setPurpose] = useState<ConfigPurpose>("script");
  const [provider, setProvider] = useState("");
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("direct");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelSeries, setModelSeries] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [isEnabled, setIsEnabled] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [validationPassed, setValidationPassed] = useState(false);

  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    enabled: open,
  });

  const refreshConfigs = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.userConfigs });
  };

  const resetForm = () => {
    setEditingConfigId(null);
    setName("");
    setDescription("");
    setPurpose("script");
    setProvider("");
    setConnectionMode("direct");
    setBaseUrl("");
    setModelSeries("");
    setApiKey("");
    setIsEnabled(true);
    setValidationPassed(false);
  };

  const saveConfigMutation = useMutation({
    mutationFn: createUserConfigAction,
    onSuccess: async () => {
      resetForm();
      setMessage(t("settings.saved"));
      await refreshConfigs();
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, t("settings.saveFailed")));
    },
  });

  const updateConfigMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UpdateUserConfigInput }) =>
      updateUserConfigAction(id, payload),
    onSuccess: async () => {
      resetForm();
      setMessage(t("settings.updated"));
      await refreshConfigs();
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, t("settings.updateFailed")));
    },
  });

  const deleteConfigMutation = useMutation({
    mutationFn: deleteUserConfigAction,
    onSuccess: async (_, deletedId) => {
      if (editingConfigId === deletedId) {
        resetForm();
      }
      setMessage(t("settings.deleted"));
      await refreshConfigs();
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, t("settings.deleteFailed")));
    },
  });

  const activateOfficialMutation = useMutation({
    mutationFn: activateOfficialConfigAction,
    onSuccess: async () => {
      setMessage(t("settings.officialActivated"));
      await refreshConfigs();
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, t("settings.officialActivateFailed")));
    },
  });

  const validateConfigMutation = useMutation({
    mutationFn: validateUserConfigAction,
    onSuccess: () => {
      setValidationPassed(true);
      setMessage(t("settings.validationPassed"));
    },
    onError: (error) => {
      setValidationPassed(false);
      setMessage(resolveRequestError(error, t("settings.validationFailed")));
    },
  });

  const options = providerOptions[purpose];
  const isMutating =
    saveConfigMutation.isPending ||
    updateConfigMutation.isPending ||
    deleteConfigMutation.isPending ||
    activateOfficialMutation.isPending ||
    validateConfigMutation.isPending;

  const hasConfigs = (configsQuery.data?.configs?.length ?? 0) > 0;
  const hasOfficialConfigs = (configsQuery.data?.officialConfigs?.length ?? 0) > 0;

  const orderedConfigs = useMemo(
    () =>
      [...(configsQuery.data?.configs ?? [])].sort(
        (a, b) => Number(b.isEnabled) - Number(a.isEnabled) || Number(b.isActive) - Number(a.isActive)
      ),
    [configsQuery.data?.configs]
  );

  const activeUserConfigByPurpose = useMemo(
    () =>
      configsByPurpose(
        configsQuery.data?.configs ?? [],
        (config) => config.isActive && config.isEnabled
      ),
    [configsQuery.data?.configs]
  );

  const officialConfigByPurpose = useMemo(
    () =>
      configsByPurpose(
        configsQuery.data?.officialConfigs ?? [],
        (config) => config.isActive && config.isEnabled && config.isVerified
      ),
    [configsQuery.data?.officialConfigs]
  );

  const activeConfigByPurpose = useMemo(
    () => ({ ...officialConfigByPurpose, ...activeUserConfigByPurpose }),
    [activeUserConfigByPurpose, officialConfigByPurpose]
  );

  const purposeLabel: Record<ConfigPurpose, string> = {
    general: t("settings.generalPurpose"),
    script: t("settings.scriptPurpose"),
    image: t("settings.imagePurpose"),
    video: t("settings.videoPurpose"),
  };

  const onPurposeChange = (nextPurpose: string | null) => {
    setValidationPassed(false);
    setMessage(null);
    const value = (nextPurpose ?? "script") as ConfigPurpose;
    const option = provider ? providerOption(value, provider) ?? defaultProviderOption(value) : null;
    const nextMode = option?.value === "custom" ? "relay" : connectionMode;
    setPurpose(value);
    if (option) {
      setProvider(option.value);
      setName(option.label);
      setConnectionMode(nextMode);
      setBaseUrl(baseUrlForConnection(value, option.value, nextMode));
      setModelSeries(option.modelSeries);
    }
  };

  const onProviderChange = (nextProvider: string | null) => {
    setValidationPassed(false);
    setMessage(null);
    const value = nextProvider ?? "";
    setProvider(value);
    const hit = value ? providerOption(purpose, value) ?? defaultProviderOption(purpose) : null;
    setName(hit?.label ?? "");
    setModelSeries(hit?.modelSeries ?? "");
    const nextMode = value === "custom" ? "relay" : "direct";
    setConnectionMode(nextMode);
    setBaseUrl(baseUrlForConnection(purpose, value, nextMode));
  };

  const onConnectionModeChange = (value: string | null) => {
    setValidationPassed(false);
    setMessage(null);
    const next = provider === "custom" ? "relay" : (value as ConnectionMode | null) ?? "direct";
    setConnectionMode(next);
    setBaseUrl(baseUrlForConnection(purpose, provider, next));
  };

  const isRelay = isRelayConnection(provider, connectionMode);
  const submitBaseUrl = baseUrl.trim();

  const validateConfig = () => {
    if (!provider) {
      setValidationPassed(false);
      setMessage(t("settings.enterProvider"));
      return;
    }

    if (!modelSeries.trim()) {
      setValidationPassed(false);
      setMessage(t("settings.enterModelSeries"));
      return;
    }

    if (isRelay && !baseUrl.trim()) {
      setValidationPassed(false);
      setMessage(t("settings.enterBaseUrl"));
      return;
    }

    if (!apiKey.trim()) {
      setValidationPassed(false);
      setMessage(t("settings.enterApiKeyBeforeValidate"));
      return;
    }

    setMessage(null);
    validateConfigMutation.mutate({
      name: name.trim(),
      description: description.trim(),
      purpose,
      provider,
      baseUrl: submitBaseUrl,
      modelSeries: modelSeries.trim(),
      apiKey: apiKey.trim(),
    });
  };

  const saveConfig = () => {
    if (!provider) {
      setMessage(t("settings.enterProvider"));
      return;
    }

    if (!modelSeries.trim()) {
      setMessage(t("settings.enterModelSeries"));
      return;
    }

    if (isRelay && !baseUrl.trim()) {
      setMessage(t("settings.enterBaseUrl"));
      return;
    }

    if (!editingConfigId && !apiKey.trim()) {
      setMessage(t("settings.enterApiKey"));
      return;
    }

    const payload: UpdateUserConfigInput = {
      name: name.trim(),
      description: description.trim(),
      purpose,
      provider,
      baseUrl: submitBaseUrl,
      modelSeries: modelSeries.trim(),
      apiKey: apiKey.trim() || undefined,
      isActive: editingConfigId ? undefined : isEnabled,
      isEnabled,
    };

    setMessage(null);

    if (editingConfigId) {
      updateConfigMutation.mutate({ id: editingConfigId, payload });
      return;
    }

    const createPayload: CreateUserConfigInput = {
      name: name.trim(),
      description: description.trim(),
      purpose,
      provider,
      baseUrl: submitBaseUrl,
      modelSeries: modelSeries.trim(),
      apiKey: apiKey.trim(),
      isActive: isEnabled,
      isEnabled,
    };

    saveConfigMutation.mutate(createPayload);
  };

  const startEdit = (config: UserConfig) => {
    setEditingConfigId(config.id);
    setName(config.name ?? "");
    setDescription(config.description ?? "");
    setPurpose(config.purpose);
    setProvider(config.provider);
    const nextMode = connectionModeFromConfig(config);
    setConnectionMode(nextMode);
    setBaseUrl(config.baseUrl || baseUrlForConnection(config.purpose, config.provider, nextMode));
    setModelSeries(config.modelSeries);
    setApiKey("");
    setIsEnabled(config.isEnabled);
    setValidationPassed(true);
    setMessage(t("settings.loadedEdit"));
  };

  const activateConfig = (config: UserConfig) => {
    if (config.isActive) {
      setMessage(null);
      updateConfigMutation.mutate({ id: config.id, payload: { isActive: false } });
      return;
    }

    if (!config.isEnabled) {
      setMessage(t("settings.disabledDefaultHint"));
      return;
    }

    setMessage(null);
    updateConfigMutation.mutate({
      id: config.id,
      payload: { isActive: true },
    });
  };

  const toggleConfigEnabled = (config: UserConfig) => {
    setMessage(null);
    updateConfigMutation.mutate({
      id: config.id,
      payload: { isEnabled: !config.isEnabled },
    });
  };

  const activateOfficialConfig = (config: UserConfig) => {
    if (!activeUserConfigByPurpose[config.purpose] && officialConfigByPurpose[config.purpose]?.id === config.id) {
      setMessage(t("settings.currentDefaultHint"));
      return;
    }

    setMessage(null);
    activateOfficialMutation.mutate(config.id);
  };

  const selectedProviderOption = providerOption(purpose, provider);

  const deleteConfig = (config: UserConfig) => {
    if (!window.confirm(t("settings.confirmDelete", { name: config.name || config.modelSeries }))) {
      return;
    }

    setMessage(null);
    deleteConfigMutation.mutate(config.id);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("settings.title")}</DialogTitle>
          <DialogDescription>{t("settings.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border border-border/80 bg-muted/40 p-3">
            <p className="text-sm font-medium">{t("settings.currentDefaults")}</p>
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              <p>
                {t("settings.generalPurpose")}：
                {displayConfigName(activeConfigByPurpose.general, t("settings.unconfigured"), t("settings.officialConfig"), t("settings.customConfig"))}
              </p>
              <p>
                {t("settings.scriptPurpose")}：
                {displayConfigName(activeConfigByPurpose.script, t("settings.unconfigured"), t("settings.officialConfig"), t("settings.customConfig"))}
              </p>
              <p>
                {t("settings.imagePurpose")}：
                {displayConfigName(activeConfigByPurpose.image, t("settings.unconfigured"), t("settings.officialConfig"), t("settings.customConfig"))}
              </p>
              <p>
                {t("settings.videoPurpose")}：
                {displayConfigName(activeConfigByPurpose.video, t("settings.unconfigured"), t("settings.officialConfig"), t("settings.customConfig"))}
              </p>
            </div>
          </div>

          <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("settings.officialConfigs")}
            </p>

            {hasOfficialConfigs
              ? (configsQuery.data?.officialConfigs ?? []).map((config) => {
                  const isCurrent =
                    !activeUserConfigByPurpose[config.purpose] &&
                    officialConfigByPurpose[config.purpose]?.id === config.id;

                  return (
                    <div key={config.id} className="rounded-md border border-border/60 bg-background px-3 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">
                            {config.name ||
                              `${purposeLabel[config.purpose]} · ${providerLabelMap[config.provider] ?? config.provider}`}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {purposeLabel[config.purpose]} · {providerLabelMap[config.provider] ?? config.provider} ·{" "}
                            {config.modelSeries}
                          </p>
                          {config.baseUrl ? (
                            <p className="mt-1 truncate text-xs text-muted-foreground">{config.baseUrl}</p>
                          ) : null}
                          {config.description ? (
                            <p className="mt-1 text-xs text-muted-foreground">{config.description}</p>
                          ) : null}
                        </div>

                        <span className="shrink-0 text-xs text-muted-foreground">{t("settings.officialConfig")}</span>
                      </div>

                      <div className="mt-3">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => activateOfficialConfig(config)}
                          disabled={isMutating}
                        >
                          <Star className={cn("mr-1 size-3.5", isCurrent && "fill-current")} />
                          {isCurrent ? t("settings.currentDefault") : t("settings.useOfficialDefault")}
                        </Button>
                      </div>
                    </div>
                  );
                })
              : null}

            {!hasOfficialConfigs ? (
              <p className="text-sm text-muted-foreground">{t("settings.officialEmpty")}</p>
            ) : null}
          </div>

          <div className="space-y-4 rounded-lg border border-border/70 bg-muted/20 p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">
                {editingConfigId ? t("settings.editConfig") : t("settings.newConfig")}
              </p>
              {editingConfigId ? (
                <Button type="button" variant="ghost" size="sm" onClick={resetForm}>
                  <X className="mr-1 size-4" />
                  {t("settings.cancelEdit")}
                </Button>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="provider">{t("settings.provider")}</Label>
              <Select value={provider} onValueChange={onProviderChange}>
                <SelectTrigger id="provider">
                  <SelectValue placeholder={t("settings.providerPlaceholder")}>
                    {provider ? providerLabelMap[provider] ?? provider : undefined}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {options.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {provider ? (
              <>
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="configName">{t("settings.name")}</Label>
                <Input
                  id="configName"
                  value={name}
                  onChange={(event) => {
                    setValidationPassed(editingConfigId !== null && !apiKey.trim());
                    setMessage(null);
                    setName(event.target.value);
                  }}
                  placeholder={t("settings.namePlaceholder")}
                  autoComplete="off"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="purpose">{t("settings.purpose")}</Label>
                <Select value={purpose} onValueChange={onPurposeChange}>
                  <SelectTrigger id="purpose">
                    <SelectValue placeholder={t("settings.purpose")}>{purposeLabel[purpose]}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">{t("settings.generalPurpose")}</SelectItem>
                    <SelectItem value="script">{t("settings.scriptPurpose")}</SelectItem>
                    <SelectItem value="image">{t("settings.imagePurpose")}</SelectItem>
                    <SelectItem value="video">{t("settings.videoPurpose")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="connectionMode">{t("settings.connectionMode")}</Label>
                  <Select value={isRelay ? "relay" : "direct"} onValueChange={onConnectionModeChange}>
                  <SelectTrigger id="connectionMode">
                    <SelectValue>{connectionModeLabel(isRelay, t("settings.officialDirect"), t("settings.customRelay"))}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {provider !== "custom" ? <SelectItem value="direct">{t("settings.officialDirect")}</SelectItem> : null}
                    <SelectItem value="relay">{t("settings.customRelay")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="modelSeries">{t("settings.modelSeries")}</Label>
                <Input
                  id="modelSeries"
                  value={modelSeries}
                  onChange={(event) => {
                    setValidationPassed(editingConfigId !== null && !apiKey.trim());
                    setMessage(null);
                    setModelSeries(event.target.value);
                  }}
                  placeholder={selectedProviderOption?.modelPlaceholder ?? t("settings.modelSeriesPlaceholder")}
                  autoComplete="off"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="baseUrl">{t("settings.baseUrl")}</Label>
              <Input
                id="baseUrl"
                value={baseUrl}
                onChange={(event) => {
                  setValidationPassed(editingConfigId !== null && !apiKey.trim());
                  setMessage(null);
                  setBaseUrl(event.target.value);
                }}
                placeholder={t("settings.baseUrlPlaceholder")}
                autoComplete="off"
                disabled={!isRelay}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="apiKey">{t("settings.apiKey")}</Label>
              <Input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(event) => {
                  setValidationPassed(false);
                  setMessage(null);
                  setApiKey(event.target.value);
                }}
                placeholder={
                  editingConfigId ? t("settings.apiKeyPlaceholderEdit") : t("settings.apiKeyPlaceholderNew")
                }
                autoComplete="off"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="configDescription">{t("settings.descriptionLabel")}</Label>
              <Textarea
                id="configDescription"
                value={description}
                onChange={(event) => {
                  setValidationPassed(editingConfigId !== null && !apiKey.trim());
                  setMessage(null);
                  setDescription(event.target.value);
                }}
                placeholder={t("settings.descriptionPlaceholder")}
                className="min-h-20"
              />
            </div>

            <Label htmlFor="configEnabled">
              <input
                id="configEnabled"
                type="checkbox"
                checked={isEnabled}
                onChange={(event) => setIsEnabled(event.target.checked)}
              />
              {t("settings.enabledConfig")}
            </Label>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Button type="button" variant="outline" onClick={validateConfig} disabled={isMutating}>
                {validateConfigMutation.isPending ? t("settings.validatingModel") : t("settings.validateModel")}
              </Button>
              <Button className="w-full" onClick={saveConfig} disabled={isMutating || !validationPassed}>
                {saveConfigMutation.isPending || updateConfigMutation.isPending
                  ? t("settings.saving")
                  : t("settings.saveAndActivate")}
              </Button>
            </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{t("settings.chooseProviderFirst")}</p>
            )}
          </div>

          <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("settings.customConfigs")}</p>

            {configsQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : null}

            {!configsQuery.isLoading && hasConfigs
              ? orderedConfigs.map((config, index) => (
                  <div
                    key={config.id}
                    className="animate-in fade-in-0 slide-in-from-bottom-1 rounded-md border border-border/60 bg-background px-3 py-3 duration-300"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {config.name ||
                            `${purposeLabel[config.purpose]} · ${providerLabelMap[config.provider] ?? config.provider}`}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {purposeLabel[config.purpose]} · {providerLabelMap[config.provider] ?? config.provider} ·{" "}
                          {config.modelSeries}
                        </p>
                        {config.baseUrl ? (
                          <p className="mt-1 truncate text-xs text-muted-foreground">{config.baseUrl}</p>
                        ) : null}
                        {config.description ? (
                          <p className="mt-1 text-xs text-muted-foreground">{config.description}</p>
                        ) : null}
                      </div>

                      <span className="shrink-0 text-xs text-muted-foreground">
                        {config.isEnabled ? t("settings.enabled") : t("settings.disabled")} ·{" "}
                        {config.isActive ? t("settings.active") : t("settings.inactive")} ·{" "}
                        {config.isVerified ? t("settings.verified") : t("settings.unverified")}
                      </span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button type="button" size="sm" variant="outline" onClick={() => startEdit(config)}>
                        <Pencil className="mr-1 size-3.5" />
                        {t("common.edit")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => activateConfig(config)}
                        disabled={isMutating}
                      >
                        <Star className={cn("mr-1 size-3.5", config.isActive && "fill-current")} />
                        {config.isActive ? t("settings.cancelDefault") : t("settings.setDefault")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => toggleConfigEnabled(config)}
                        disabled={isMutating}
                      >
                        <Power className="mr-1 size-3.5" />
                        {config.isEnabled ? t("settings.disable") : t("settings.enable")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => deleteConfig(config)}
                        disabled={isMutating}
                      >
                        <Trash2 className="mr-1 size-3.5" />
                        {t("common.delete")}
                      </Button>
                    </div>
                  </div>
                ))
              : null}

            {!configsQuery.isLoading && !hasConfigs ? (
              <p className="text-sm text-muted-foreground">{t("settings.empty")}</p>
            ) : null}
          </div>

          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
