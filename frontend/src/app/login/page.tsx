"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { loginAction } from "@/actions/auth-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n";
import { resolveRequestError } from "@/lib/http/errors";
import { useUserStore } from "@/store/user-store";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const setAuth = useUserStore((state) => state.setAuth);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: loginAction,
    onSuccess: (data) => {
      setAuth(data.token, data.user);
      router.replace("/");
    },
    onError: (requestError) => {
      setError(resolveRequestError(requestError, t("auth.loginFailed")));
    },
  });

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setError(null);

    loginMutation.mutate({
      username,
      password,
    });
  };

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-background p-6">
      <PreferencesSwitcher className="absolute top-6 right-6" />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{t("auth.loginTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <Label htmlFor="username">{t("auth.username")}</Label>
              <Input
                id="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">{t("auth.password")}</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button className="w-full" type="submit" disabled={loginMutation.isPending}>
              {loginMutation.isPending ? t("auth.loggingIn") : t("auth.login")}
            </Button>
          </form>
          <p className="mt-4 text-sm text-muted-foreground">
            {t("auth.noAccount")}
            <Link href="/register" className="ml-1 text-foreground underline">
              {t("auth.goRegister")}
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
