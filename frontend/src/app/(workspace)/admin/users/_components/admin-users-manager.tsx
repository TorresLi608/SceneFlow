"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import {
  createAdminUserAction,
  deleteAdminUserAction,
  listAdminUsersAction,
  resetAdminUserPasswordAction,
  updateAdminUserAction,
} from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { AuthUser } from "@/types/auth";

import { filterUsers, type UserRoleFilter, type UserStatusFilter } from "./user-list";

const pageSize = 10;
const emptyUsers: AuthUser[] = [];

export function AdminUsersManager() {
  const { t, formatDateTime } = useI18n();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<UserRoleFilter>("all");
  const [statusFilter, setStatusFilter] = useState<UserStatusFilter>("all");
  const [page, setPage] = useState(1);
  const [message, setMessage] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [resetResult, setResetResult] = useState<{ username: string; password: string } | null>(null);

  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers,
    queryFn: listAdminUsersAction,
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ id, isDisabled }: { id: number; isDisabled: boolean }) => updateAdminUserAction(id, { isDisabled }),
    onSuccess: async () => {
      setMessage(t("admin.userStatusUpdated"));
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("admin.updateUserFailed"))),
  });

  const createUserMutation = useMutation({
    mutationFn: createAdminUserAction,
    onSuccess: async () => {
      setCreateOpen(false);
      setUsername("");
      setPassword("");
      setMessage(t("admin.userCreated"));
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("admin.createUserFailed"))),
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ id }: { id: number; username: string }) => resetAdminUserPasswordAction(id),
    onSuccess: (data, user) => setResetResult({ username: user.username, password: data.password }),
    onError: (error) => setMessage(resolveRequestError(error, t("admin.resetPasswordFailed"))),
  });

  const deleteUserMutation = useMutation({
    mutationFn: deleteAdminUserAction,
    onSuccess: async () => {
      setMessage(t("admin.userDeleted"));
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("admin.deleteUserFailed"))),
  });

  const users = usersQuery.data?.users ?? emptyUsers;
  const filteredUsers = useMemo(
    () => filterUsers(users, search, roleFilter, statusFilter),
    [roleFilter, search, statusFilter, users]
  );
  const pageCount = Math.max(1, Math.ceil(filteredUsers.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageUsers = filteredUsers.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const isMutating = updateUserMutation.isPending || deleteUserMutation.isPending || resetPasswordMutation.isPending;

  const deleteUser = (id: number, username: string) => {
    if (window.confirm(t("admin.confirmDeleteUser", { username }))) deleteUserMutation.mutate(id);
  };

  const resetPassword = (id: number, username: string) => {
    if (window.confirm(t("admin.confirmResetPassword", { username }))) resetPasswordMutation.mutate({ id, username });
  };

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("admin.registeredUsers")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.usersDescription")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" />
          {t("admin.createUser")}
        </Button>
      </div>

      <div className="grid gap-3 rounded-lg border border-border/70 bg-muted/20 p-3 md:grid-cols-3 xl:grid-cols-[minmax(220px,1fr)_180px_180px]">
        <Input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder={t("admin.searchUsers")}
        />
        <Select
          value={roleFilter}
          onValueChange={(value) => {
            setRoleFilter((value ?? "all") as UserRoleFilter);
            setPage(1);
          }}
        >
          <SelectTrigger>
            <SelectValue>
              {roleFilter === "all"
                ? t("admin.allRoles")
                : roleFilter === "superAdmin"
                  ? t("admin.roleSuperAdmin")
                  : t("admin.roleUser")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("admin.allRoles")}</SelectItem>
            <SelectItem value="user">{t("admin.roleUser")}</SelectItem>
            <SelectItem value="superAdmin">{t("admin.roleSuperAdmin")}</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={statusFilter}
          onValueChange={(value) => {
            setStatusFilter((value ?? "all") as UserStatusFilter);
            setPage(1);
          }}
        >
          <SelectTrigger>
            <SelectValue>
              {statusFilter === "all"
                ? t("admin.allStatuses")
                : statusFilter === "disabled"
                  ? t("admin.userDisabled")
                  : t("common.statusNormal")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("admin.allStatuses")}</SelectItem>
            <SelectItem value="active">{t("common.statusNormal")}</SelectItem>
            <SelectItem value="disabled">{t("admin.userDisabled")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border/70">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">{t("settings.name")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.tableRole")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.status")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.tableCreatedAt")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.tableUpdatedAt")}</th>
              <th className="px-3 py-2 text-center font-medium">{t("admin.tableActions")}</th>
            </tr>
          </thead>
          <tbody>
            {pageUsers.map((item) => {
              const isProtected = item.role === "superAdmin";
              return (
                <tr key={item.id} className="border-t border-border/70">
                  <td className="px-3 py-3">
                    <p className="font-medium">{item.username}</p>
                    <p className="mt-1 text-xs text-muted-foreground">ID {item.id}</p>
                  </td>
                  <td className="px-3 py-3">
                    <Badge variant={isProtected ? "default" : "secondary"}>
                      {isProtected ? t("admin.roleSuperAdmin") : t("admin.roleUser")}
                    </Badge>
                  </td>
                  <td className="px-3 py-3">
                    <Badge variant={item.isDisabled ? "destructive" : "outline"}>
                      {item.isDisabled ? t("admin.userDisabled") : t("common.statusNormal")}
                    </Badge>
                  </td>
                  <td className="px-3 py-3 text-muted-foreground">{formatDateTime(item.createdAt)}</td>
                  <td className="px-3 py-3 text-muted-foreground">{formatDateTime(item.updatedAt)}</td>
                  <td className="px-3 py-3">
                    <div className="flex justify-center items-center gap-2">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        disabled={isProtected || isMutating}
                        onClick={() => resetPassword(item.id, item.username)}
                        aria-label={t("admin.resetPassword")}
                        title={t("admin.resetPassword")}
                      >
                        <KeyRound className="size-4" />
                      </Button>
                      <Switch
                        checked={!item.isDisabled}
                        disabled={isProtected || isMutating}
                        onCheckedChange={(enabled) => updateUserMutation.mutate({ id: item.id, isDisabled: !enabled })}
                        aria-label={item.isDisabled ? t("admin.enable") : t("admin.disable")}
                        title={item.isDisabled ? t("admin.enable") : t("admin.disable")}
                      />
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        disabled={isProtected || isMutating}
                        onClick={() => deleteUser(item.id, item.username)}
                        aria-label={t("common.delete")}
                        title={t("common.delete")}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {usersQuery.isLoading ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">{t("common.loading")}</td>
              </tr>
            ) : null}
            {!usersQuery.isLoading && pageUsers.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">{t("admin.noMatchingUsers")}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
        <span>{t("admin.pagination", { total: filteredUsers.length, page: currentPage, pageCount })}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
            {t("common.previous")}
          </Button>
          <Button variant="outline" size="sm" disabled={currentPage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>
            {t("common.next")}
          </Button>
        </div>
      </div>

      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin.createUser")}</DialogTitle>
            <DialogDescription>{t("admin.createUserDescription")}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              createUserMutation.mutate({ username: username.trim(), password });
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="adminCreateUsername">{t("auth.username")}</Label>
              <Input
                id="adminCreateUsername"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                minLength={3}
                maxLength={64}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="adminCreatePassword">{t("auth.password")}</Label>
              <Input
                id="adminCreatePassword"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={6}
                maxLength={128}
                required
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                <X className="size-4" />
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={createUserMutation.isPending}>
                {createUserMutation.isPending ? t("common.loading") : t("admin.createUser")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(resetResult)} onOpenChange={(open) => !open && setResetResult(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin.passwordReset")}</DialogTitle>
            <DialogDescription>{t("admin.passwordResetDescription", { username: resetResult?.username ?? "" })}</DialogDescription>
          </DialogHeader>
          <Input value={resetResult?.password ?? ""} readOnly onFocus={(event) => event.currentTarget.select()} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
