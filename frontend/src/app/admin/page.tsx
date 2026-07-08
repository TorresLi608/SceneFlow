"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Shield, Star, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  createOfficialConfigAction,
  deleteAdminUserAction,
  deleteOfficialConfigAction,
  listAdminUsersAction,
  listOfficialConfigsAction,
  updateAdminUserAction,
  updateOfficialConfigAction,
} from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import {
  allProviderOptions,
  configsByPurpose,
  defaultProviderOption,
  providerLabelMap,
  providerOption,
} from "@/lib/model-providers";
import { useUserStore } from "@/store/user-store";
import type { ConfigPurpose, UserConfig } from "@/types/auth";

const purposeLabel: Record<ConfigPurpose, string> = {
  general: "通用",
  script: "文本",
  image: "图片生成",
  video: "视频生成",
};

const defaultConfigProvider = defaultProviderOption();
type ConnectionMode = "direct" | "relay";

function connectionModeLabel(isRelay: boolean) {
  return isRelay ? "自定义中转站" : "官方直连";
}

export default function AdminPage() {
  const queryClient = useQueryClient();
  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const user = useUserStore((state) => state.user);
  const setUser = useUserStore((state) => state.setUser);
  const logout = useUserStore((state) => state.logout);

  const [view, setView] = useState<"models" | "users">("models");
  const [editingConfigId, setEditingConfigId] = useState<number | null>(null);
  const [name, setName] = useState(defaultConfigProvider.label);
  const [description, setDescription] = useState("");
  const [purpose, setPurpose] = useState<ConfigPurpose>("script");
  const [provider, setProvider] = useState(defaultConfigProvider.value);
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("direct");
  const [baseUrl, setBaseUrl] = useState(defaultConfigProvider.baseUrl ?? "");
  const [modelSeries, setModelSeries] = useState(defaultConfigProvider.modelSeries);
  const [apiKey, setApiKey] = useState("");
  const [isActive, setIsActive] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token),
  });

  const currentUser = meQuery.data?.user ?? user;
  const isSuperAdmin = currentUser?.role === "superAdmin";

  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers,
    queryFn: listAdminUsersAction,
    enabled: Boolean(isSuperAdmin),
  });

  const officialConfigsQuery = useQuery({
    queryKey: queryKeys.officialConfigs,
    queryFn: listOfficialConfigsAction,
    enabled: Boolean(isSuperAdmin),
  });

  useEffect(() => {
    if (meQuery.data?.user) {
      setUser(meQuery.data.user);
    }
  }, [meQuery.data?.user, setUser]);

  const options = allProviderOptions;
  const officialConfigs = useMemo(() => officialConfigsQuery.data?.configs ?? [], [officialConfigsQuery.data?.configs]);

  const resetForm = () => {
    const option = defaultProviderOption();
    setEditingConfigId(null);
    setName(option.label);
    setDescription("");
    setPurpose("script");
    setProvider(option.value);
    setConnectionMode("direct");
    setBaseUrl(option.baseUrl ?? "");
    setModelSeries(option.modelSeries);
    setApiKey("");
    setIsActive(false);
  };

  const refreshModels = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.officialConfigs }),
      queryClient.invalidateQueries({ queryKey: queryKeys.userConfigs }),
    ]);
  };

  const createConfigMutation = useMutation({
    mutationFn: createOfficialConfigAction,
    onSuccess: async () => {
      resetForm();
      setMessage("官方配置已保存。");
      await refreshModels();
    },
    onError: (error) => setMessage(resolveRequestError(error, "保存官方配置失败")),
  });

  const updateConfigMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<UserConfig> & { apiKey?: string } }) =>
      updateOfficialConfigAction(id, payload),
    onSuccess: async () => {
      resetForm();
      setMessage("官方配置已更新。");
      await refreshModels();
    },
    onError: (error) => setMessage(resolveRequestError(error, "更新官方配置失败")),
  });

  const deleteConfigMutation = useMutation({
    mutationFn: deleteOfficialConfigAction,
    onSuccess: async () => {
      setMessage("官方配置已删除。");
      await refreshModels();
    },
    onError: (error) => setMessage(resolveRequestError(error, "删除官方配置失败")),
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ id, isDisabled }: { id: number; isDisabled: boolean }) => updateAdminUserAction(id, { isDisabled }),
    onSuccess: async () => {
      setMessage("用户状态已更新。");
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => setMessage(resolveRequestError(error, "更新用户状态失败")),
  });

  const deleteUserMutation = useMutation({
    mutationFn: deleteAdminUserAction,
    onSuccess: async () => {
      setMessage("用户已删除。");
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => setMessage(resolveRequestError(error, "删除用户失败")),
  });

  const isMutating =
    createConfigMutation.isPending ||
    updateConfigMutation.isPending ||
    deleteConfigMutation.isPending ||
    updateUserMutation.isPending ||
    deleteUserMutation.isPending;

  const currentOfficialByPurpose = useMemo(
    () => configsByPurpose(officialConfigs, (config) => config.isActive),
    [officialConfigs]
  );

  const onPurposeChange = (nextPurpose: string | null) => {
    const value = (nextPurpose ?? "script") as ConfigPurpose;
    setPurpose(value);
    if (connectionMode === "direct") {
      setBaseUrl(providerOption(value, provider)?.baseUrl ?? "");
    }
  };

  const onProviderChange = (nextProvider: string | null) => {
    const value = nextProvider ?? options[0]?.value ?? "qwen";
    setProvider(value);
    const option = providerOption(purpose, value);
    setName(option?.label ?? "");
    setConnectionMode(value === "custom" ? "relay" : "direct");
    setBaseUrl(value === "custom" ? "" : option?.baseUrl ?? "");
    setModelSeries(option?.modelSeries ?? "");
  };

  const isRelay = connectionMode === "relay" || provider === "custom";

  const onConnectionModeChange = (value: string | null) => {
    const next = provider === "custom" ? "relay" : (value as ConnectionMode | null) ?? "direct";
    setConnectionMode(next);
    setBaseUrl(next === "direct" ? providerOption(purpose, provider)?.baseUrl ?? "" : "");
  };

  const startEdit = (config: UserConfig) => {
    setEditingConfigId(config.id);
    setName(config.name);
    setDescription(config.description);
    setPurpose(config.purpose);
    setProvider(config.provider);
    setConnectionMode(config.baseUrl || config.provider === "custom" ? "relay" : "direct");
    setBaseUrl(config.baseUrl || providerOption(config.purpose, config.provider)?.baseUrl || "");
    setModelSeries(config.modelSeries);
    setApiKey("");
    setIsActive(config.isActive);
    setMessage("已载入官方配置，API Key 留空则沿用原 Key。");
  };

  const saveConfig = () => {
    if (!modelSeries.trim()) {
      setMessage("请输入模型系列。");
      return;
    }

    if (isRelay && !baseUrl.trim()) {
      setMessage("请输入自定义中转 Base URL。");
      return;
    }

    if (!editingConfigId && isActive && !apiKey.trim()) {
      setMessage("启用官方默认前请输入 API Key；不启用时可以先保存草稿。");
      return;
    }

    const payload = {
      name: name.trim(),
      description: description.trim(),
      purpose,
      provider,
      baseUrl: baseUrl.trim(),
      modelSeries: modelSeries.trim(),
      apiKey: apiKey.trim() || undefined,
      isActive,
    };

    setMessage(null);
    if (editingConfigId) {
      updateConfigMutation.mutate({ id: editingConfigId, payload });
      return;
    }
    createConfigMutation.mutate({ ...payload, apiKey: apiKey.trim() });
  };

  const deleteConfig = (config: UserConfig) => {
    if (!window.confirm(`确认删除官方配置「${config.name || config.modelSeries}」吗？`)) {
      return;
    }
    deleteConfigMutation.mutate(config.id);
  };

  const deleteUser = (id: number, username: string) => {
    if (!window.confirm(`确认删除用户「${username}」吗？`)) {
      return;
    }
    deleteUserMutation.mutate(id);
  };

  if (!hydrated || meQuery.isLoading) {
    return <main className="min-h-screen bg-background p-6 text-sm text-muted-foreground">加载中...</main>;
  }

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>需要登录</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>请使用 superAdmin 账号登录后进入管理后台。</p>
            <Button render={<Link href="/login" />}>去登录</Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (!isSuperAdmin) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>无权限</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>当前账号不是 superAdmin。</p>
            <div className="flex gap-2">
              <Button variant="outline" render={<Link href="/" />}>返回工作台</Button>
              <Button
                variant="secondary"
                onClick={() => {
                  logout();
                  window.location.href = "/login";
                }}
              >
                退出登录
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border/70 px-4 py-4 md:px-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-3.5" />
              返回工作台
            </Link>
            <h1 className="mt-2 flex items-center gap-2 text-xl font-semibold">
              <Shield className="size-5" />
              SceneFlow 管理后台
            </h1>
          </div>
          <div className="flex gap-2">
            <Button variant={view === "models" ? "default" : "outline"} onClick={() => setView("models")}>
              官方配置
            </Button>
            <Button variant={view === "users" ? "default" : "outline"} onClick={() => setView("users")}>
              用户管理
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-4 p-4 md:p-6">
        {view === "models" ? (
          <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
            <Card className="h-fit">
              <CardHeader>
                <CardTitle>{editingConfigId ? "编辑官方配置" : "新增官方配置"}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="officialName">名称</Label>
                  <Input id="officialName" value={name} onChange={(event) => setName(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="officialPurpose">用途</Label>
                  <Select value={purpose} onValueChange={onPurposeChange}>
                    <SelectTrigger id="officialPurpose" className="w-full">
                      <SelectValue>{purposeLabel[purpose]}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="general">通用</SelectItem>
                      <SelectItem value="script">文本</SelectItem>
                      <SelectItem value="image">图片生成</SelectItem>
                      <SelectItem value="video">视频生成</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="officialProvider">供应商</Label>
                  <Select value={provider} onValueChange={onProviderChange}>
                    <SelectTrigger id="officialProvider" className="w-full">
                      <SelectValue>{providerLabelMap[provider] ?? provider}</SelectValue>
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
                  <Label htmlFor="officialConnection">接入方式</Label>
                  <Select value={isRelay ? "relay" : "direct"} onValueChange={onConnectionModeChange}>
                    <SelectTrigger id="officialConnection" className="w-full">
                      <SelectValue>{connectionModeLabel(isRelay)}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {provider !== "custom" ? <SelectItem value="direct">官方直连</SelectItem> : null}
                      <SelectItem value="relay">自定义中转站</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="officialModel">模型系列</Label>
                  <Input
                    id="officialModel"
                    value={modelSeries}
                    onChange={(event) => setModelSeries(event.target.value)}
                    placeholder={providerOption(purpose, provider)?.modelPlaceholder}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="officialBaseUrl">Base URL</Label>
                  <Input
                    id="officialBaseUrl"
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder="https://api.example.com/v1"
                    disabled={!isRelay}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="officialKey">API Key</Label>
                  <Input
                    id="officialKey"
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder={editingConfigId ? "留空则沿用原 Key" : "输入官方 API Key"}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="officialDescription">描述</Label>
                  <Textarea id="officialDescription" value={description} onChange={(event) => setDescription(event.target.value)} />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
                  作为该用途官方默认
                </label>
                <div className="flex gap-2">
                  <Button onClick={saveConfig} disabled={isMutating}>
                    {isMutating ? "保存中..." : "保存"}
                  </Button>
                  {editingConfigId ? (
                    <Button variant="outline" onClick={resetForm}>
                      <X className="size-4" />
                      取消
                    </Button>
                  ) : null}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>官方配置</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {officialConfigs.map((config) => (
                  <div key={config.id} className="rounded-md border border-border/70 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {config.name || `${purposeLabel[config.purpose]} · ${providerLabelMap[config.provider] ?? config.provider}`}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {purposeLabel[config.purpose]} · {providerLabelMap[config.provider] ?? config.provider} · {config.modelSeries}
                        </p>
                        {config.baseUrl ? <p className="mt-1 truncate text-xs text-muted-foreground">{config.baseUrl}</p> : null}
                        {config.description ? <p className="mt-1 text-xs text-muted-foreground">{config.description}</p> : null}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Badge variant={config.isActive ? "default" : "outline"}>
                          {config.isActive ? "默认" : "未启用"}
                        </Badge>
                        <Badge variant={config.isVerified ? "secondary" : "destructive"}>
                          {config.isVerified ? "已校验" : "未校验"}
                        </Badge>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => startEdit(config)}>
                        <Pencil className="size-3.5" />
                        编辑
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => updateConfigMutation.mutate({ id: config.id, payload: { isActive: true } })}
                        disabled={isMutating || currentOfficialByPurpose[config.purpose]?.id === config.id}
                      >
                        <Star className="size-3.5" />
                        设为官方默认
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => deleteConfig(config)} disabled={isMutating}>
                        <Trash2 className="size-3.5" />
                        删除
                      </Button>
                    </div>
                  </div>
                ))}
                {!officialConfigsQuery.isLoading && officialConfigs.length === 0 ? (
                  <p className="text-sm text-muted-foreground">还没有官方模型配置。</p>
                ) : null}
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>已注册用户</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(usersQuery.data?.users ?? []).map((item) => (
                <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/70 p-3">
                  <div>
                    <p className="text-sm font-medium">{item.username}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      ID {item.id} · {item.role} · {item.isDisabled ? "已禁用" : "正常"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={item.role === "superAdmin" || isMutating}
                      onClick={() => updateUserMutation.mutate({ id: item.id, isDisabled: !item.isDisabled })}
                    >
                      {item.isDisabled ? "启用" : "禁用"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={item.role === "superAdmin" || isMutating}
                      onClick={() => deleteUser(item.id, item.username)}
                    >
                      删除
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
      </div>
    </main>
  );
}
