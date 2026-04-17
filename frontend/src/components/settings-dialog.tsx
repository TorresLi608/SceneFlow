"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Star, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import {
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
import { resolveRequestError } from "@/lib/http/errors";
import type { ConfigPurpose, CreateUserConfigInput, UpdateUserConfigInput, UserConfig } from "@/types/auth";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}

const providerOptions: Record<
  ConfigPurpose,
  Array<{ value: string; label: string; modelSeries: string }>
> = {
  script: [
    { value: "qwen", label: "千问", modelSeries: "qwen-plus" },
    { value: "deepseek", label: "DeepSeek", modelSeries: "deepseek-chat" },
    { value: "doubao", label: "豆包", modelSeries: "doubao-seed-1-6-250615" },
    { value: "openai", label: "OpenAI", modelSeries: "gpt-4o-mini" },
  ],
  image: [
    { value: "qwen", label: "千问", modelSeries: "qwen-plus" },
    { value: "deepseek", label: "DeepSeek", modelSeries: "deepseek-chat" },
    { value: "doubao", label: "豆包", modelSeries: "doubao-seed-1-6-250615" },
    { value: "openai", label: "OpenAI", modelSeries: "gpt-4o-mini" },
  ],
  video: [{ value: "seedance2.0", label: "Seedance 2.0", modelSeries: "seedance-2.0" }],
};

const purposeLabel: Record<ConfigPurpose, string> = {
  script: "剧本/提示词",
  image: "图片生成",
  video: "视频生成",
};

const providerLabelMap: Record<string, string> = {
  qwen: "千问",
  deepseek: "DeepSeek",
  doubao: "豆包",
  openai: "OpenAI",
  "seedance2.0": "Seedance 2.0",
};

function displayConfigName(config?: UserConfig) {
  if (!config) {
    return "未配置";
  }

  if (config.name?.trim()) {
    return `${config.name} · ${config.modelSeries}`;
  }

  const providerLabel = providerLabelMap[config.provider] ?? config.provider;
  return `${providerLabel} · ${config.modelSeries}`;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const queryClient = useQueryClient();

  const [editingConfigId, setEditingConfigId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [purpose, setPurpose] = useState<ConfigPurpose>("script");
  const [provider, setProvider] = useState("qwen");
  const [modelSeries, setModelSeries] = useState("qwen-plus");
  const [apiKey, setApiKey] = useState("");
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
    setProvider("qwen");
    setModelSeries("qwen-plus");
    setApiKey("");
    setValidationPassed(false);
  };

  const saveConfigMutation = useMutation({
    mutationFn: createUserConfigAction,
    onSuccess: async () => {
      resetForm();
      setMessage("配置已保存并激活");
      await refreshConfigs();
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, "保存失败，请稍后重试"));
    },
  });

  const updateConfigMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UpdateUserConfigInput }) =>
      updateUserConfigAction(id, payload),
    onSuccess: async () => {
      resetForm();
      setMessage("配置已更新");
      await refreshConfigs();
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, "更新失败，请稍后重试"));
    },
  });

  const deleteConfigMutation = useMutation({
    mutationFn: deleteUserConfigAction,
    onSuccess: async (_, deletedId) => {
      if (editingConfigId === deletedId) {
        resetForm();
      }
      setMessage("配置已删除");
      await refreshConfigs();
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, "删除失败，请稍后重试"));
    },
  });

  const validateConfigMutation = useMutation({
    mutationFn: validateUserConfigAction,
    onSuccess: () => {
      setValidationPassed(true);
      setMessage("模型校验通过，可保存配置。");
    },
    onError: (error) => {
      setValidationPassed(false);
      setMessage(resolveRequestError(error, "模型校验失败，请检查 provider / modelSeries / key"));
    },
  });

  const options = providerOptions[purpose];
  const isMutating =
    saveConfigMutation.isPending ||
    updateConfigMutation.isPending ||
    deleteConfigMutation.isPending ||
    validateConfigMutation.isPending;

  const hasConfigs = (configsQuery.data?.configs?.length ?? 0) > 0;

  const orderedConfigs = useMemo(
    () => [...(configsQuery.data?.configs ?? [])].sort((a, b) => Number(b.isActive) - Number(a.isActive)),
    [configsQuery.data?.configs]
  );

  const activeConfigByPurpose = useMemo(
    () =>
      (configsQuery.data?.configs ?? []).reduce<Partial<Record<ConfigPurpose, UserConfig>>>((acc, config) => {
        if (config.isActive && !acc[config.purpose]) {
          acc[config.purpose] = config;
        }
        return acc;
      }, {}),
    [configsQuery.data?.configs]
  );

  const onPurposeChange = (nextPurpose: string | null) => {
    setValidationPassed(editingConfigId !== null && !apiKey.trim());
    setMessage(null);
    const value = (nextPurpose ?? "script") as ConfigPurpose;
    setPurpose(value);
    const nextOption = providerOptions[value][0];
    if (nextOption) {
      setProvider(nextOption.value);
      setModelSeries(nextOption.modelSeries);
    }
  };

  const onProviderChange = (nextProvider: string | null) => {
    setValidationPassed(editingConfigId !== null && !apiKey.trim());
    setMessage(null);
    const value = nextProvider ?? options[0]?.value ?? "qwen";
    setProvider(value);
    const hit = options.find((item) => item.value === value);
    if (hit) {
      setModelSeries(hit.modelSeries);
    }
  };

  const validateConfig = () => {
    if (!apiKey.trim()) {
      setValidationPassed(false);
      setMessage("请先输入 API Key，再进行校验。编辑已有配置时，不改 Key 可直接保存。");
      return;
    }

    setMessage(null);
    validateConfigMutation.mutate({
      name: name.trim(),
      description: description.trim(),
      purpose,
      provider,
      modelSeries: modelSeries.trim(),
      apiKey: apiKey.trim(),
    });
  };

  const saveConfig = () => {
    if (!editingConfigId && !apiKey.trim()) {
      setMessage("请输入 API Key");
      return;
    }

    const payload: UpdateUserConfigInput = {
      name: name.trim(),
      description: description.trim(),
      purpose,
      provider,
      modelSeries: modelSeries.trim(),
      apiKey: apiKey.trim() || undefined,
      isActive: true,
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
      modelSeries: modelSeries.trim(),
      apiKey: apiKey.trim(),
      isActive: true,
    };

    saveConfigMutation.mutate(createPayload);
  };

  const startEdit = (config: UserConfig) => {
    setEditingConfigId(config.id);
    setName(config.name ?? "");
    setDescription(config.description ?? "");
    setPurpose(config.purpose);
    setProvider(config.provider);
    setModelSeries(config.modelSeries);
    setApiKey("");
    setValidationPassed(true);
    setMessage("已载入配置，若不修改 API Key 可直接保存。");
  };

  const activateConfig = (config: UserConfig) => {
    setMessage(null);
    updateConfigMutation.mutate({
      id: config.id,
      payload: { isActive: true },
    });
  };

  const deleteConfig = (config: UserConfig) => {
    if (!window.confirm(`确认删除配置「${config.name || config.modelSeries}」吗？`)) {
      return;
    }

    setMessage(null);
    deleteConfigMutation.mutate(config.id);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>AI Provider 配置中心</DialogTitle>
          <DialogDescription>
            按应用用途设置默认模型。每个已保存配置都可以编辑、删除，并可切换为当前用途的默认模型。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border border-border/80 bg-muted/40 p-3">
            <p className="text-sm font-medium">当前应用默认模型</p>
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              <p>剧本/提示词：{displayConfigName(activeConfigByPurpose.script)}</p>
              <p>图片生成：{displayConfigName(activeConfigByPurpose.image)}</p>
              <p>视频生成：{displayConfigName(activeConfigByPurpose.video)}</p>
            </div>
          </div>

          <div className="space-y-4 rounded-lg border border-border/70 bg-muted/20 p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">{editingConfigId ? "编辑配置" : "新增配置"}</p>
              {editingConfigId ? (
                <Button type="button" variant="ghost" size="sm" onClick={resetForm}>
                  <X className="mr-1 size-4" />
                  取消编辑
                </Button>
              ) : null}
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="configName">名称</Label>
                <Input
                  id="configName"
                  value={name}
                  onChange={(event) => {
                    setValidationPassed(editingConfigId !== null && !apiKey.trim());
                    setMessage(null);
                    setName(event.target.value);
                  }}
                  placeholder="例如：剧本默认千问 / 图片豆包"
                  autoComplete="off"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="purpose">用途</Label>
                <Select value={purpose} onValueChange={onPurposeChange}>
                  <SelectTrigger id="purpose">
                    <SelectValue placeholder="选择用途" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="script">剧本/提示词</SelectItem>
                    <SelectItem value="image">图片生成</SelectItem>
                    <SelectItem value="video">视频生成</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="configDescription">描述</Label>
              <Textarea
                id="configDescription"
                value={description}
                onChange={(event) => {
                  setValidationPassed(editingConfigId !== null && !apiKey.trim());
                  setMessage(null);
                  setDescription(event.target.value);
                }}
                placeholder="可选。说明这个模型配置适合做什么，例如长文剧本优化、快速出图、高清图像生成。"
                className="min-h-20"
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="provider">Provider</Label>
                <Select value={provider} onValueChange={onProviderChange}>
                  <SelectTrigger id="provider">
                    <SelectValue placeholder="选择 Provider" />
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

              <div className="space-y-2">
                <Label htmlFor="modelSeries">模型系列</Label>
                <Input
                  id="modelSeries"
                  value={modelSeries}
                  onChange={(event) => {
                    setValidationPassed(editingConfigId !== null && !apiKey.trim());
                    setMessage(null);
                    setModelSeries(event.target.value);
                  }}
                  placeholder="例如 qwen-plus / deepseek-chat / seedance-2.0"
                  autoComplete="off"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="apiKey">API Key</Label>
              <Input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(event) => {
                  setValidationPassed(false);
                  setMessage(null);
                  setApiKey(event.target.value);
                }}
                placeholder={editingConfigId ? "留空则沿用原 Key，填写则更新 Key" : "输入对应 provider 的 key"}
                autoComplete="off"
              />
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Button type="button" variant="outline" onClick={validateConfig} disabled={isMutating}>
                {validateConfigMutation.isPending ? "校验中..." : "校验模型可用性"}
              </Button>
              <Button className="w-full" onClick={saveConfig} disabled={isMutating || !validationPassed}>
                {saveConfigMutation.isPending || updateConfigMutation.isPending ? "保存中..." : "保存并激活"}
              </Button>
            </div>
          </div>

          <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">已保存配置</p>

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
                        {config.description ? (
                          <p className="mt-1 text-xs text-muted-foreground">{config.description}</p>
                        ) : null}
                      </div>

                      <span className="shrink-0 text-xs text-muted-foreground">
                        {config.isActive ? "Active" : "Inactive"} · {config.isVerified ? "Verified" : "Unverified"}
                      </span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button type="button" size="sm" variant="outline" onClick={() => startEdit(config)}>
                        <Pencil className="mr-1 size-3.5" />
                        编辑
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => activateConfig(config)}
                        disabled={config.isActive || isMutating}
                      >
                        <Star className="mr-1 size-3.5" />
                        设为默认
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => deleteConfig(config)}
                        disabled={isMutating}
                      >
                        <Trash2 className="mr-1 size-3.5" />
                        删除
                      </Button>
                    </div>
                  </div>
                ))
              : null}

            {!configsQuery.isLoading && !hasConfigs ? (
              <p className="text-sm text-muted-foreground">还没有保存任何配置。</p>
            ) : null}
          </div>

          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
