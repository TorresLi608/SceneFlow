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

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const queryClient = useQueryClient();

  const [provider, setProvider] = useState("OpenAI");
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
      provider,
      apiKey,
      isActive: true,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>全局模型与密钥设置</DialogTitle>
          <DialogDescription>
            保存你自己的第三方 API Key，后续解析与生成将走你的配置。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="provider">Provider</Label>
            <Select value={provider} onValueChange={(value) => setProvider(value ?? "OpenAI")}>
              <SelectTrigger id="provider">
                <SelectValue placeholder="选择 Provider" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="OpenAI">OpenAI</SelectItem>
                <SelectItem value="DeepSeek">DeepSeek</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="apiKey">API Key</Label>
            <Input
              id="apiKey"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-..."
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
                    <span className="text-sm">{config.provider}</span>
                    <span className="text-xs text-muted-foreground">
                      {config.isActive ? "Active" : "Inactive"}
                    </span>
                  </div>
                ))
              : null}

            {!configsQuery.isLoading && !hasConfigs ? (
              <p className="text-sm text-muted-foreground">还没有保存任何 API Key。</p>
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
