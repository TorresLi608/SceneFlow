"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Pencil, Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import {
  createOfficialConfigAction,
  deleteOfficialConfigAction,
  listOfficialConfigsAction,
  updateOfficialConfigAction,
} from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import {
  activateOfficialConfigAction,
  createUserConfigAction,
  deleteUserConfigAction,
  listUserConfigsAction,
  updateUserConfigAction,
} from "@/actions/settings-actions";
import { Badge } from "@/components/ui/badge";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import {
  baseUrlForConnection,
  connectionModeFromConfig,
  configsByPurpose,
  type ConnectionMode,
  defaultProviderOption,
  isRelayConnection,
  providerLabel,
  providerOption,
  providerOptions,
} from "@/lib/model-providers";
import { useUserStore } from "@/store/user-store";
import type { ConfigPurpose, UserConfig } from "@/types/auth";

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

function isDefaultConfig(config: UserConfig, activeUserByPurpose: Partial<Record<ConfigPurpose, UserConfig>>) {
  if (config.source === "user") {
    return config.isActive;
  }
  return !activeUserByPurpose[config.purpose] && config.isActive;
}

export function ModelConfigManager() {
  const { t } = useI18n();
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
  const [message, setMessage] = useState<string | null>(null);
  const [viewingConfig, setViewingConfig] = useState<UserConfig | null>(null);
  const [editingConfig, setEditingConfig] = useState<UserConfig | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const [isOfficial, setIsOfficial] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [purpose, setPurpose] = useState<ConfigPurpose>("script");
  const [provider, setProvider] = useState(defaultOption.value);
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("direct");
  const [baseUrl, setBaseUrl] = useState(defaultOption.baseUrl ?? "");
  const [modelSeries, setModelSeries] = useState(defaultOption.modelSeries);
  const [apiKey, setApiKey] = useState("");
  const [isEnabled, setIsEnabled] = useState(true);
  const [isDefault, setIsDefault] = useState(false);
  const purposeLabel: Record<ConfigPurpose, string> = {
    general: t("settings.generalPurpose"),
    script: t("settings.scriptPurpose"),
    image: t("settings.imagePurpose"),
    video: t("settings.videoPurpose"),
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

  const userConfigs = userQuery.data?.configs ?? emptyConfigs;
  const officialConfigs = isSuperAdmin ? officialQuery.data?.configs ?? emptyConfigs : userQuery.data?.officialConfigs ?? emptyConfigs;
  const activeUserByPurpose = useMemo(
    () => configsByPurpose(userConfigs, (config) => config.isActive && config.isEnabled),
    [userConfigs]
  );

  const rows = useMemo(() => [...officialConfigs, ...userConfigs], [officialConfigs, userConfigs]);
  const providerFilters = useMemo(
    () => Array.from(new Set(Object.values(providerOptions).flat().map((option) => option.value))).filter(Boolean),
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
  }, [activeUserByPurpose, defaultFilter, enabledFilter, providerFilter, purposeFilter, rows, search, sourceFilter]);

  const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageRows = filteredRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const options = providerOptions[purpose];
  const isRelay = isRelayConnection(provider, connectionMode);
  const selectedProviderOption = providerOption(purpose, provider);
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
    setIsEnabled(true);
    setIsDefault(false);
  };

  const openCreate = () => {
    resetForm();
    setFormOpen(true);
  };

  const openEdit = (config: UserConfig) => {
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
    setApiKey("");
    setIsEnabled(config.isEnabled);
    setIsDefault(isDefaultConfig(config, activeUserByPurpose));
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
  };

  const onConnectionModeChange = (value: string | null) => {
    const mode = provider === "custom" ? "relay" : (value as ConnectionMode | null) ?? "direct";
    setConnectionMode(mode);
    setBaseUrl(baseUrlForConnection(purpose, provider, mode));
  };

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
      if (!editingConfig && !saveAsOfficial && !apiKey.trim()) {
        throw new Error(t("admin.userConfigNeedsApiKey"));
      }
      if (!editingConfig && saveAsOfficial && isDefault && !apiKey.trim()) {
        throw new Error(t("admin.officialDefaultNeedsApiKey"));
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
      };

      if (editingConfig) {
        if (editingConfig.source === "official") {
          await updateOfficialConfigAction(editingConfig.id, payload);
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
      setMessage(t("admin.saveConfigSuccess"));
      await refreshConfigs();
    },
    onError: (error) => setMessage(resolveRequestError(error, error instanceof Error ? error.message : t("admin.saveConfigFailed"))),
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
      setMessage(t("admin.defaultUpdated"));
      await refreshConfigs();
    },
    onError: (error) => setMessage(resolveRequestError(error, error instanceof Error ? error.message : t("admin.updateDefaultFailed"))),
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
      setMessage(t("admin.enabledUpdated"));
      await refreshConfigs();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("admin.updateEnabledFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: (config: UserConfig) => {
      if (config.source === "official" && !isSuperAdmin) {
        throw new Error(t("admin.noDeleteOfficialPermission"));
      }
      return config.source === "official" ? deleteOfficialConfigAction(config.id) : deleteUserConfigAction(config.id);
    },
    onSuccess: async () => {
      setMessage(t("admin.configDeleted"));
      await refreshConfigs();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("admin.deleteConfigFailed"))),
  });

  const busy = saveMutation.isPending || defaultMutation.isPending || enabledMutation.isPending || deleteMutation.isPending || isMutating;

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("admin.configTitle")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.configDescription")}</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="size-4" />
          {t("settings.newConfig")}
        </Button>
      </div>

      <div className="grid gap-3 rounded-lg border border-border/70 bg-muted/20 p-3 md:grid-cols-2 xl:grid-cols-[minmax(180px,1fr)_150px_150px_150px_150px_150px]">
        <Input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder={t("admin.searchConfig")}
        />
        <Select value={purposeFilter} onValueChange={(value) => {
          setPurposeFilter((value ?? "all") as "all" | ConfigPurpose);
          setPage(1);
        }}>
          <SelectTrigger>
            <SelectValue>{purposeFilter === "all" ? t("admin.allPurposes") : purposeLabel[purposeFilter]}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("admin.allPurposes")}</SelectItem>
            {Object.entries(purposeLabel).map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={providerFilter} onValueChange={(value) => {
          setProviderFilter(value ?? "all");
          setPage(1);
        }}>
          <SelectTrigger>
            <SelectValue>{providerFilter === "all" ? t("admin.allProviders") : providerLabel(providerFilter, t)}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("admin.allProviders")}</SelectItem>
            {providerFilters.map((value) => (
              <SelectItem key={value} value={value}>{providerLabel(value, t)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={sourceFilter} onValueChange={(value) => {
          setSourceFilter((value ?? "all") as SourceFilter);
          setPage(1);
        }}>
          <SelectTrigger>
            <SelectValue>{sourceFilter === "all" ? t("admin.allSources") : sourceFilter === "official" ? t("settings.officialConfig") : t("admin.userConfig")}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("admin.allSources")}</SelectItem>
            <SelectItem value="official">{t("settings.officialConfig")}</SelectItem>
            <SelectItem value="user">{t("admin.userConfig")}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={defaultFilter} onValueChange={(value) => {
          setDefaultFilter((value ?? "all") as DefaultFilter);
          setPage(1);
        }}>
          <SelectTrigger>
            <SelectValue>{defaultFilter === "all" ? t("admin.allDefaults") : defaultFilter === "default" ? t("admin.default") : t("admin.notDefault")}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("admin.allDefaults")}</SelectItem>
            <SelectItem value="default">{t("admin.default")}</SelectItem>
            <SelectItem value="not-default">{t("admin.notDefault")}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={enabledFilter} onValueChange={(value) => {
          setEnabledFilter((value ?? "all") as EnabledFilter);
          setPage(1);
        }}>
          <SelectTrigger>
            <SelectValue>{enabledFilter === "all" ? t("admin.allStatuses") : enabledFilter === "enabled" ? t("settings.enable") : t("settings.disable")}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("admin.allStatuses")}</SelectItem>
            <SelectItem value="enabled">{t("settings.enable")}</SelectItem>
            <SelectItem value="disabled">{t("settings.disable")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border/70">
        <table className="w-full min-w-[980px] text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">{t("settings.name")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("settings.purpose")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("settings.provider")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.tableModel")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.status")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.tableDefault")}</th>
              <th className="px-3 py-2 text-right font-medium">{t("admin.tableActions")}</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((config) => {
              const checked = isDefaultConfig(config, activeUserByPurpose);
              const canManageConfig = config.source === "user" || isSuperAdmin;
              return (
                <tr key={rowKey(config)} className="border-t border-border/70">
                  <td className="max-w-64 px-3 py-3">
                    <p className="truncate font-medium">{configTitle(config, purposeLabel, t)}</p>
                    <p className="mt-1 truncate text-xs text-muted-foreground">{config.description || config.baseUrl || "-"}</p>
                  </td>
                  <td className="px-3 py-3">{purposeLabel[config.purpose]}</td>
                  <td className="px-3 py-3">{providerLabel(config.provider, t)}</td>
                  <td className="max-w-44 truncate px-3 py-3">{config.modelSeries}</td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1">
                      <Badge variant={config.source === "official" ? "default" : "secondary"}>
                        {config.source === "official" ? t("config.source.official") : t("config.source.user")}
                      </Badge>
                      <Badge variant={config.isEnabled ? "outline" : "destructive"}>
                        {config.isEnabled ? t("settings.enable") : t("settings.disable")}
                      </Badge>
                      <Badge variant={config.isVerified ? "outline" : "destructive"}>
                        {config.isVerified ? t("settings.verified") : t("settings.unverified")}
                      </Badge>
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <Switch
                      checked={checked}
                      disabled={busy || !config.isEnabled}
                      onCheckedChange={(next) => defaultMutation.mutate({ config, checked: next })}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex justify-end gap-1">
                      <Button size="icon-sm" variant="ghost" onClick={() => setViewingConfig(config)} title={t("admin.view")}>
                        <Eye className="size-4" />
                      </Button>
                      <Button size="icon-sm" variant="ghost" disabled={!canManageConfig} onClick={() => openEdit(config)} title={t("common.edit")}>
                        <Pencil className="size-4" />
                      </Button>
                      <Switch
                        checked={config.isEnabled}
                        disabled={busy || !canManageConfig}
                        onCheckedChange={() => enabledMutation.mutate(config)}
                        className="mx-1 self-center"
                      />
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        disabled={busy || !canManageConfig}
                        onClick={() => {
                          if (window.confirm(t("admin.confirmDeleteConfig", { name: configTitle(config, purposeLabel, t) }))) {
                            deleteMutation.mutate(config);
                          }
                        }}
                        title={t("common.delete")}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!busy && pageRows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">{t("admin.noMatchingConfigs")}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
        <span>{t("admin.pagination", { total: filteredRows.length, page: currentPage, pageCount })}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>{t("common.previous")}</Button>
          <Button variant="outline" size="sm" disabled={currentPage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>{t("common.next")}</Button>
        </div>
      </div>

      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingConfig ? t("settings.editConfig") : t("settings.newConfig")}</DialogTitle>
            <DialogDescription>{t("admin.emptyApiKeyKeepsCurrent")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            {isSuperAdmin ? (
              <label className="flex items-center justify-between rounded-lg border border-border/70 p-3 text-sm">
                <span>{t("admin.asOfficialConfig")}</span>
                <Switch checked={isOfficial} disabled={Boolean(editingConfig)} onCheckedChange={setIsOfficial} />
              </label>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="adminConfigPurpose">{t("settings.purpose")}</Label>
                <Select value={purpose} onValueChange={onPurposeChange}>
                  <SelectTrigger id="adminConfigPurpose"><SelectValue>{purposeLabel[purpose]}</SelectValue></SelectTrigger>
                  <SelectContent>
                    {Object.entries(purposeLabel).map(([value, label]) => (
                      <SelectItem key={value} value={value}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="adminConfigProvider">{t("settings.provider")}</Label>
                <Select value={provider} onValueChange={onProviderChange}>
                  <SelectTrigger id="adminConfigProvider"><SelectValue>{providerLabel(provider, t)}</SelectValue></SelectTrigger>
                  <SelectContent>
                    {options.map((option) => (
                      <SelectItem key={option.value} value={option.value}>{providerLabel(option.value, t)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="adminConfigName">{t("settings.name")}</Label>
                <Input id="adminConfigName" value={name} onChange={(event) => setName(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="adminConfigConnection">{t("settings.connectionMode")}</Label>
                <Select value={isRelay ? "relay" : "direct"} onValueChange={onConnectionModeChange}>
                  <SelectTrigger id="adminConfigConnection"><SelectValue>{isRelay ? t("admin.connectionRelay") : t("settings.officialDirect")}</SelectValue></SelectTrigger>
                  <SelectContent>
                    {provider !== "custom" ? <SelectItem value="direct">{t("settings.officialDirect")}</SelectItem> : null}
                    <SelectItem value="relay">{t("admin.connectionRelay")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="adminConfigModel">{t("settings.modelSeries")}</Label>
                <Input
                  id="adminConfigModel"
                  value={modelSeries}
                  onChange={(event) => setModelSeries(event.target.value)}
                  placeholder={selectedProviderOption?.modelPlaceholder}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="adminConfigBaseUrl">Base URL</Label>
                <Input
                  id="adminConfigBaseUrl"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  disabled={!isRelay}
                  placeholder="https://api.example.com/v1"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="adminConfigKey">API Key</Label>
              <Input
                id="adminConfigKey"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={editingConfig ? t("admin.apiKeyKeepCurrent") : t("admin.apiKeyInput")}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="adminConfigDescription">{t("settings.descriptionLabel")}</Label>
              <Textarea id="adminConfigDescription" value={description} onChange={(event) => setDescription(event.target.value)} />
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex items-center justify-between rounded-lg border border-border/70 p-3 text-sm">
                <span>{t("admin.enabledStatus")}</span>
                <Switch checked={isEnabled} onCheckedChange={setIsEnabled} />
              </label>
              <label className="flex items-center justify-between rounded-lg border border-border/70 p-3 text-sm">
                <span>{t("admin.setDefault")}</span>
                <Switch checked={isDefault} onCheckedChange={setIsDefault} />
              </label>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setFormOpen(false)}>
                <X className="size-4" />
                {t("common.cancel")}
              </Button>
              <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                {saveMutation.isPending ? t("settings.saving") : t("common.save")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(viewingConfig)} onOpenChange={(open) => !open && setViewingConfig(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{viewingConfig ? configTitle(viewingConfig, purposeLabel, t) : t("admin.configDetails")}</DialogTitle>
            <DialogDescription>{viewingConfig?.description || t("common.noDescription")}</DialogDescription>
          </DialogHeader>
          {viewingConfig ? (
            <div className="grid gap-2 text-sm">
              <p>{t("admin.source")}: {viewingConfig.source === "official" ? t("settings.officialConfig") : t("admin.userConfig")}</p>
              <p>{t("settings.purpose")}: {purposeLabel[viewingConfig.purpose]}</p>
              <p>{t("settings.provider")}: {providerLabel(viewingConfig.provider, t)}</p>
              <p>{t("admin.tableModel")}: {viewingConfig.modelSeries}</p>
              <p className="break-all">Base URL：{viewingConfig.baseUrl || "-"}</p>
              <p>{t("admin.status")}: {viewingConfig.isEnabled ? t("settings.enable") : t("settings.disable")} / {viewingConfig.isVerified ? t("settings.verified") : t("settings.unverified")}</p>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
