"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  deleteAdminUserAction,
  listAdminUsersAction,
  updateAdminUserAction,
} from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { resolveRequestError } from "@/lib/http/errors";

export function AdminUsersManager() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);

  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers,
    queryFn: listAdminUsersAction,
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

  const isMutating = updateUserMutation.isPending || deleteUserMutation.isPending;

  const deleteUser = (id: number, username: string) => {
    if (window.confirm(`确认删除用户「${username}」吗？`)) {
      deleteUserMutation.mutate(id);
    }
  };

  return (
    <div>
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

      {message ? <p className="mt-4 text-sm text-muted-foreground">{message}</p> : null}
    </div>
  );
}
