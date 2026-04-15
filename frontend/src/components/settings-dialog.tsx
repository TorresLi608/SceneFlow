"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { createUserConfigAction, listUserConfigsAction } from "@/actions/settings-actions";
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
import { resolveRequestError } from "@/lib/http/errors";
import type { ConfigPurpose } from "@/types/auth";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}

const providerOptions: Record<ConfigPurpose, Array<{ value: string; label: string; model: string }>> = {
  script: [
    { value: "qwen", label: "千问", model: "qwen-plus" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat" },
    { value: "doubao", label: "豆包", model: "doubao-seed-1-6-250615" },
    { value: "openai", label: "OpenAI", model: "gpt-4o-mini" },
  ],
  image: [
    { value: "qwen", label: "千问", model: "qwen-plus" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat" },
    { value: "doubao", label: "豆包", model: "doubao-seed-1-6-250615" },
    { value: "openai", label: "OpenAI", model: "gpt-4o-mini" },
  ],
  video: [{ value: "seedance2.0", label: "Seedance 2.0", model: "seedance-2.0" }],
};

const purposeLabel: Record<ConfigPurpose, string> = {
  script: "剧本/提示词",
  image: "图片生成",
  video: "视频生成",
};

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const queryClient = useQueryClient();

  const [purpose, setPurpose] = useState<ConfigPurpose>("script");
  const [provider, setProvider] = useState("qwen");
  const [model, setModel] = useState("qwen-plus");
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    enabled: open,
  });

  const saveConfigMutation = useMutation({
    mutationFn: createUserConfigAction,
    onSuccess: async () => {
      setMessage("配置已保存并激活");
      setApiKey("");
      await queryClient.invalidateQueries({ queryKey: queryKeys.userConfigs });
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, "保存失败，请稍后重试"));
    },
  });

  const options = providerOptions[purpose];

  const hasConfigs = (configsQuery.data?.configs?.length ?? 0) > 0;

  const orderedConfigs = useMemo(
    () => [...(configsQuery.data?.configs ?? [])].sort((a, b) => Number(b.isActive) - Number(a.isActive)),
    [configsQuery.data?.configs]
  );

  const saveConfig = () => {
    if (!apiKey.trim()) {
      setMessage("请输入 API Key");
      return;
    }

    setMessage(null);
    saveConfigMutation.mutate({
      purpose,
      provider,
      model,
      apiKey,
      isActive: true,
    });
  };

  const onPurposeChange = (nextPurpose: string | null) => {
    const value = (nextPurpose ?? "script") as ConfigPurpose;
    setPurpose(value);
    const nextOption = providerOptions[value][0];
    if (nextOption) {
      setProvider(nextOption.value);
      setModel(nextOption.model);
    }
  };

  const onProviderChange = (nextProvider: string | null) => {
    const value = nextProvider ?? options[0]?.value ?? "qwen";
    setProvider(value);
    const hit = options.find((item) => item.value === value);
    if (hit) {
      setModel(hit.model);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>AI Provider 配置中心</DialogTitle>
          <DialogDescription>
            按用途配置模型与密钥：剧本/分镜/图片建议使用千问、DeepSeek、豆包；视频仅支持 Seedance 2.0。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
          </div>

          <div className="space-y-2">
            <Label htmlFor="model">模型 ID</Label>
            <Input
              id="model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="例如 qwen-plus / seedance-2.0"
              autoComplete="off"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="apiKey">API Key</Label>
            <Input
              id="apiKey"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="输入对应 provider 的 key"
              autoComplete="off"
            />
          </div>

          <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">已保存配置</p>

            {configsQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-2/3" />
              </div>
            ) : null}

            {!configsQuery.isLoading && hasConfigs
              ? orderedConfigs.map((config, index) => (
                  <div
                    key={config.id}
                    className="animate-in fade-in-0 slide-in-from-bottom-1 flex items-center justify-between rounded-md border border-border/60 bg-background px-3 py-2 duration-300"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <span className="text-sm">
                      {purposeLabel[config.purpose]} · {config.provider} · {config.model}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {config.isActive ? "Active" : "Inactive"}
                    </span>
                  </div>
                ))
              : null}

            {!configsQuery.isLoading && !hasConfigs ? (
              <p className="text-sm text-muted-foreground">还没有保存任何配置。</p>
            ) : null}
          </div>

          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

          <Button className="w-full" onClick={saveConfig} disabled={saveConfigMutation.isPending}>
            {saveConfigMutation.isPending ? "保存中..." : "保存并激活"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
