"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, Plus, RotateCcw, Trash2, X } from "lucide-react";
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
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
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
  const [createOpen, setCreateOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AuthUser["role"]>("user");
  const [level, setLevel] = useState<1 | 2 | 3>(1);
  const [resetResult, setResetResult] = useState<{ username: string; password: string } | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ type: "delete" | "reset"; id: number; username: string } | null>(null);

  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers,
    queryFn: listAdminUsersAction,
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { isDisabled?: boolean; level?: 1 | 2 | 3 } }) => updateAdminUserAction(id, payload),
    onSuccess: async () => {
      toast.add({ title: t("admin.userStatusUpdated"), type: "success" });
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => toast.add({ title: resolveRequestError(error, t("admin.updateUserFailed")), type: "error", priority: "high" }),
  });

  const createUserMutation = useMutation({
    mutationFn: createAdminUserAction,
    onSuccess: async () => {
      setCreateOpen(false);
      setUsername("");
      setPassword("");
      setRole("user");
      setLevel(1);
      toast.add({ title: t("admin.userCreated"), type: "success" });
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => toast.add({ title: resolveRequestError(error, t("admin.createUserFailed")), type: "error", priority: "high" }),
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ id }: { id: number; username: string }) => resetAdminUserPasswordAction(id),
    onSuccess: (data, user) => {
      setResetResult({ username: user.username, password: data.password });
      toast.add({ title: t("admin.passwordReset"), type: "success" });
    },
    onError: (error) => toast.add({ title: resolveRequestError(error, t("admin.resetPasswordFailed")), type: "error", priority: "high" }),
  });

  const deleteUserMutation = useMutation({
    mutationFn: deleteAdminUserAction,
    onSuccess: async () => {
      toast.add({ title: t("admin.userDeleted"), type: "success" });
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => toast.add({ title: resolveRequestError(error, t("admin.deleteUserFailed")), type: "error", priority: "high" }),
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
  const filtersActive = Boolean(search.trim()) || roleFilter !== "all" || statusFilter !== "all";

  const createRoleItems = useMemo(
    () => [
      { value: "user", label: t("admin.roleUser") },
      { value: "superAdmin", label: t("admin.roleSuperAdmin") },
    ],
    [t]
  );
  const roleItems = useMemo(
    () => [{ value: "all", label: t("admin.allRoles") }, ...createRoleItems],
    [createRoleItems, t]
  );
  const statusItems = useMemo(
    () => [
      { value: "all", label: t("admin.allStatuses") },
      { value: "active", label: t("common.statusNormal") },
      { value: "disabled", label: t("admin.userDisabled") },
    ],
    [t]
  );
  const levelItems = useMemo(
    () => ([1, 2, 3] as const).map((level) => ({ value: String(level), label: t("admin.levelValue", { level }) })),
    [t]
  );

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("admin.registeredUsers")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.usersDescription")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus data-icon="inline-start" />
          {t("admin.createUser")}
        </Button>
      </div>

      <div className="grid gap-3 rounded-lg border border-border/70 bg-muted/20 p-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1fr)_180px_180px_auto]">
        <Input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder={t("admin.searchUsers")}
        />
        <Select
          items={roleItems}
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
            <SelectGroup>{roleItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup>
          </SelectContent>
        </Select>
        <Select
          items={statusItems}
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
            <SelectGroup>{statusItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup>
          </SelectContent>
        </Select>
        {filtersActive ? (
          <Button variant="outline" onClick={() => { setSearch(""); setRoleFilter("all"); setStatusFilter("all"); setPage(1); }}>
            <RotateCcw data-icon="inline-start" />
            {t("common.clearFilters")}
          </Button>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table className="min-w-[980px]">
          <TableHeader>
            <TableRow>
              <TableHead>{t("settings.name")}</TableHead>
              <TableHead>{t("admin.tableRole")}</TableHead>
              <TableHead>{t("admin.userLevel")}</TableHead>
              <TableHead>{t("admin.status")}</TableHead>
              <TableHead>{t("admin.tableCreatedAt")}</TableHead>
              <TableHead>{t("admin.tableUpdatedAt")}</TableHead>
              <TableHead className="text-center">{t("admin.tableActions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageUsers.map((item) => {
              const isProtected = item.role === "superAdmin";
              return (
                <TableRow key={item.id}>
                  <TableCell>
                    <p className="font-medium">{item.username}</p>
                    <p className="mt-1 text-xs text-muted-foreground">ID {item.id}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant={isProtected ? "default" : "secondary"}>
                      {isProtected ? t("admin.roleSuperAdmin") : t("admin.roleUser")}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Select
                      items={levelItems}
                      value={String(item.level)}
                      disabled={isProtected || isMutating}
                      onValueChange={(value) => updateUserMutation.mutate({ id: item.id, payload: { level: Number(value) as 1 | 2 | 3 } })}
                    >
                      <SelectTrigger className="w-24"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectGroup>{levelItems.map((level) => <SelectItem key={level.value} value={level.value}>{level.label}</SelectItem>)}</SelectGroup></SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.isDisabled ? "destructive" : "outline"}>
                      {item.isDisabled ? t("admin.userDisabled") : t("common.statusNormal")}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDateTime(item.createdAt)}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDateTime(item.updatedAt)}</TableCell>
                  <TableCell>
                    <div className="flex justify-center items-center gap-2">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        disabled={isProtected || isMutating}
                        onClick={() => setConfirmAction({ type: "reset", id: item.id, username: item.username })}
                        aria-label={t("admin.resetPassword")}
                        title={t("admin.resetPassword")}
                      >
                        <KeyRound />
                      </Button>
                      <Switch
                        checked={!item.isDisabled}
                        disabled={isProtected || isMutating}
                        onCheckedChange={(enabled) => updateUserMutation.mutate({ id: item.id, payload: { isDisabled: !enabled } })}
                        aria-label={item.isDisabled ? t("admin.enable") : t("admin.disable")}
                        title={item.isDisabled ? t("admin.enable") : t("admin.disable")}
                      />
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        disabled={isProtected || isMutating}
                        onClick={() => setConfirmAction({ type: "delete", id: item.id, username: item.username })}
                        aria-label={t("common.delete")}
                        title={t("common.delete")}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
            {usersQuery.isLoading ? (
              <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">{t("common.loading")}</TableCell></TableRow>
            ) : null}
            {!usersQuery.isLoading && pageUsers.length === 0 ? (
              <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">{t("admin.noMatchingUsers")}</TableCell></TableRow>
            ) : null}
          </TableBody>
        </Table>
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

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin.createUser")}</DialogTitle>
            <DialogDescription>{t("admin.createUserDescription")}</DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              createUserMutation.mutate({ username: username.trim(), password, role, level });
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="adminCreateUsername">{t("auth.username")}</FieldLabel>
                <Input id="adminCreateUsername" value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={64} required />
              </Field>
              <Field>
                <FieldLabel htmlFor="adminCreatePassword">{t("auth.password")}</FieldLabel>
                <Input id="adminCreatePassword" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} maxLength={128} required />
              </Field>
              <Field>
                <FieldLabel htmlFor="adminCreateRole">{t("admin.tableRole")}</FieldLabel>
                <Select items={createRoleItems} value={role} onValueChange={(value) => setRole((value ?? "user") as AuthUser["role"])}>
                  <SelectTrigger id="adminCreateRole"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectGroup>{createRoleItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="adminCreateLevel">{t("admin.userLevel")}</FieldLabel>
                <Select items={levelItems} value={String(level)} onValueChange={(value) => setLevel(Number(value) as 1 | 2 | 3)}>
                  <SelectTrigger id="adminCreateLevel"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectGroup>{levelItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
                </Select>
              </Field>
            </FieldGroup>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                <X data-icon="inline-start" />
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={createUserMutation.isPending}>
                {createUserMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Plus data-icon="inline-start" />}
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

      <Dialog open={Boolean(confirmAction)} onOpenChange={(open) => !open && setConfirmAction(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmAction?.type === "delete" ? t("common.delete") : t("admin.resetPassword")}</DialogTitle>
            <DialogDescription>
              {confirmAction?.type === "delete"
                ? t("admin.confirmDeleteUser", { username: confirmAction?.username ?? "" })
                : t("admin.confirmResetPassword", { username: confirmAction?.username ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmAction(null)}>{t("common.cancel")}</Button>
            <Button
              variant={confirmAction?.type === "delete" ? "destructive" : "default"}
              onClick={() => {
                if (!confirmAction) return;
                if (confirmAction.type === "delete") deleteUserMutation.mutate(confirmAction.id);
                else resetPasswordMutation.mutate({ id: confirmAction.id, username: confirmAction.username });
                setConfirmAction(null);
              }}
            >
              {confirmAction?.type === "delete" ? <Trash2 data-icon="inline-start" /> : <KeyRound data-icon="inline-start" />}
              {confirmAction?.type === "delete" ? t("common.delete") : t("admin.resetPassword")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
