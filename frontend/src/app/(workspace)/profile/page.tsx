"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coins, Loader2, ReceiptText, Send, UserRound } from "lucide-react";
import { useState } from "react";

import { queryKeys } from "@/actions/query-keys";
import { getMeAction, redeemCodeAction, updateMeAction } from "@/actions/user-actions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { formatMoney } from "@/lib/money";
import { useUserStore } from "@/store/user-store";

export default function ProfilePage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const setUser = useUserStore((state) => state.setUser);
  const [username, setUsername] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState<{ title: string; description: string } | null>(null);
  const meQuery = useQuery({ queryKey: queryKeys.me, queryFn: getMeAction });
  const user = meQuery.data?.user;
  const usernameValue = username ?? user?.username ?? "";

  const updateMutation = useMutation({
    mutationFn: () => updateMeAction({ username: usernameValue.trim() }),
    onSuccess: (data) => {
      setUser(data.user);
      queryClient.setQueryData(queryKeys.me, data);
      setUsername(null);
      setMessage({ title: t("profile.saveSuccess"), description: data.user.username });
    },
    onError: (error) => setMessage({ title: t("profile.saveFailed"), description: resolveRequestError(error, t("profile.saveFailed")) }),
  });
  const redeemMutation = useMutation({
    mutationFn: () => redeemCodeAction(code.trim()),
    onSuccess: (data) => {
      setUser(data.user);
      queryClient.setQueryData(queryKeys.me, { user: data.user });
      setCode("");
      setMessage({
        title: t("profile.redeemSuccess", { amount: (data.amountMicros / 1_000_000).toFixed(2) }),
        description: formatMoney(data.user.balanceMicros),
      });
    },
    onError: (error) => setMessage({ title: t("profile.redeemFailed"), description: resolveRequestError(error, t("profile.redeemFailed")) }),
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
                <AvatarFallback className="text-lg">{user?.username.slice(0, 2).toUpperCase() || "SF"}</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <CardTitle className="truncate text-lg">{user?.username ?? t("common.loading")}</CardTitle>
                <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{t("admin.levelValue", { level: user?.level ?? 1 })}</Badge>
                  <span>{t("profile.userId")}: {user?.id ?? "—"}</span>
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-3">
            <ProfileMetric icon={Coins} label={t("profile.balance")} value={formatMoney(user?.balanceMicros ?? 0)} />
            <ProfileMetric icon={ReceiptText} label={t("profile.historicalCost")} value={formatMoney(user?.historicalCostMicros ?? 0)} />
            <ProfileMetric icon={Send} label={t("profile.requestCount")} value={new Intl.NumberFormat().format(user?.requestCount ?? 0)} />
          </CardContent>
        </Card>

        {message ? (
          <Alert>
            <AlertTitle>{message.title}</AlertTitle>
            <AlertDescription>{message.description}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{t("profile.redeemTitle")}</CardTitle>
              <CardDescription>{t("profile.redeemDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={(event) => { event.preventDefault(); redeemMutation.mutate(); }}>
                <FieldGroup>
                  <Field data-invalid={Boolean(message?.title === t("profile.redeemFailed")) || undefined}>
                    <FieldLabel htmlFor="redemptionCode">{t("profile.redeemCode")}</FieldLabel>
                    <Input
                      id="redemptionCode"
                      value={code}
                      onChange={(event) => setCode(event.target.value.toUpperCase())}
                      placeholder={t("profile.redeemPlaceholder")}
                      aria-invalid={Boolean(message?.title === t("profile.redeemFailed")) || undefined}
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
                  <Button type="submit" disabled={updateMutation.isPending || usernameValue.trim() === user?.username}>
                    {updateMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <UserRound data-icon="inline-start" />}
                    {updateMutation.isPending ? t("common.loading") : t("common.save")}
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
