"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coins, KeyRound, Loader2, ReceiptText, Send, UserRound } from "lucide-react";
import { useState } from "react";

import { queryKeys } from "@/actions/query-keys";
import { changePasswordAction, getMeAction, redeemCodeAction, updateMeAction } from "@/actions/user-actions";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { formatMicros, formatMoney } from "@/lib/money";
import { useUserStore } from "@/store/user-store";

export default function ProfilePage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const setUser = useUserStore((state) => state.setUser);
  const [username, setUsername] = useState<string | null>(null);
  const [nickname, setNickname] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const meQuery = useQuery({ queryKey: queryKeys.me, queryFn: getMeAction });
  const user = meQuery.data?.user;
  const usernameValue = username ?? user?.username ?? "";
  const nicknameValue = nickname ?? user?.nickname ?? "";

  const updateMutation = useMutation({
    mutationFn: () => updateMeAction({ username: usernameValue.trim(), nickname: nicknameValue.trim() }),
    onSuccess: (data) => {
      setUser(data.user);
      queryClient.setQueryData(queryKeys.me, data);
      setUsername(null);
      setNickname(null);
      toast.add({ title: t("profile.saveSuccess"), description: data.user.nickname || data.user.username, type: "success" });
    },
    onError: (error) => toast.add({ title: t("profile.saveFailed"), description: resolveRequestError(error, t("profile.saveFailed")), type: "error", priority: "high" }),
  });
  const redeemMutation = useMutation({
    mutationFn: () => redeemCodeAction(code.trim()),
    onSuccess: (data) => {
      setUser(data.user);
      queryClient.setQueryData(queryKeys.me, { user: data.user });
      setCode("");
      toast.add({
        title: t("profile.redeemSuccess", { amount: formatMicros(data.amountMicros, 6) }),
        description: formatMoney(data.user.balanceMicros, 6),
        type: "success",
      });
    },
    onError: (error) => toast.add({ title: t("profile.redeemFailed"), description: resolveRequestError(error, t("profile.redeemFailed")), type: "error", priority: "high" }),
  });
  const passwordMutation = useMutation({
    mutationFn: () => changePasswordAction(currentPassword, newPassword),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast.add({ title: t("profile.passwordSuccess"), description: t("profile.passwordSuccessDescription"), type: "success" });
    },
    onError: (error) => toast.add({ title: t("profile.passwordFailed"), description: resolveRequestError(error, t("profile.passwordFailed")), type: "error", priority: "high" }),
  });

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-5">
        <div>
          <h2 className="text-xl font-semibold">{t("profile.title")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("profile.description")}</p>
        </div>

        <Card>
          <CardHeader className="border-b">
            <div className="flex flex-wrap items-center gap-4">
              <Avatar className="size-16">
                <AvatarFallback className="text-lg">{(user?.nickname || user?.username)?.slice(0, 2).toUpperCase() || "SF"}</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <CardTitle className="truncate text-lg">{user?.nickname || user?.username || t("common.loading")}</CardTitle>
                <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{t("admin.levelValue", { level: user?.level ?? 1 })}</Badge>
                  <span>{t("profile.userId")}: {user?.id ?? "—"}</span>
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-3">
            <ProfileMetric icon={Coins} label={t("profile.balance")} value={formatMoney(user?.balanceMicros ?? "0", 6)} />
            <ProfileMetric icon={ReceiptText} label={t("profile.historicalCost")} value={formatMoney(user?.historicalCostMicros ?? "0", 6)} />
            <ProfileMetric icon={Send} label={t("profile.requestCount")} value={new Intl.NumberFormat().format(user?.requestCount ?? 0)} />
          </CardContent>
        </Card>

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{t("profile.redeemTitle")}</CardTitle>
              <CardDescription>{t("profile.redeemDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={(event) => { event.preventDefault(); redeemMutation.mutate(); }}>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="redemptionCode">{t("profile.redeemCode")}</FieldLabel>
                    <Input
                      id="redemptionCode"
                      value={code}
                      onChange={(event) => setCode(event.target.value.toUpperCase())}
                      placeholder={t("profile.redeemPlaceholder")}
                      maxLength={64}
                      required
                    />
                    <FieldDescription>{t("profile.redeemDescription")}</FieldDescription>
                  </Field>
                  <Button type="submit" disabled={redeemMutation.isPending || code.trim().length < 4}>
                    {redeemMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Coins data-icon="inline-start" />}
                    {redeemMutation.isPending ? t("profile.redeeming") : t("profile.redeem")}
                  </Button>
                </FieldGroup>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("profile.accountTitle")}</CardTitle>
              <CardDescription>{t("profile.accountDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={(event) => { event.preventDefault(); updateMutation.mutate(); }}>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="profileUsername">{t("auth.username")}</FieldLabel>
                    <Input id="profileUsername" value={usernameValue} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={64} required />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="profileNickname">{t("auth.nickname")}</FieldLabel>
                    <Input id="profileNickname" value={nicknameValue} onChange={(event) => setNickname(event.target.value)} maxLength={64} placeholder={t("auth.nicknamePlaceholder")} />
                  </Field>
                  <Button type="submit" disabled={updateMutation.isPending || (usernameValue.trim() === user?.username && nicknameValue.trim() === user?.nickname)}>
                    {updateMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <UserRound data-icon="inline-start" />}
                    {updateMutation.isPending ? t("common.loading") : t("common.save")}
                  </Button>
                </FieldGroup>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("profile.passwordTitle")}</CardTitle>
              <CardDescription>{t("profile.passwordDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={(event) => {
                event.preventDefault();
                if (newPassword !== confirmPassword) {
                  toast.add({ title: t("profile.passwordFailed"), description: t("auth.passwordMismatch"), type: "error", priority: "high" });
                  return;
                }
                passwordMutation.mutate();
              }}>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="currentPassword">{t("profile.currentPassword")}</FieldLabel>
                    <Input id="currentPassword" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} maxLength={128} autoComplete="current-password" required />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="newPassword">{t("profile.newPassword")}</FieldLabel>
                    <Input id="newPassword" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={6} maxLength={128} autoComplete="new-password" required />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="confirmNewPassword">{t("profile.confirmNewPassword")}</FieldLabel>
                    <Input id="confirmNewPassword" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={6} maxLength={128} autoComplete="new-password" required />
                  </Field>
                  <Button type="submit" disabled={passwordMutation.isPending}>
                    {passwordMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <KeyRound data-icon="inline-start" />}
                    {passwordMutation.isPending ? t("profile.changingPassword") : t("profile.changePassword")}
                  </Button>
                </FieldGroup>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ProfileMetric({ icon: Icon, label, value }: { icon: typeof Coins; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border p-4">
      <div className="flex size-10 items-center justify-center rounded-lg bg-muted"><Icon /></div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      </div>
    </div>
  );
}
