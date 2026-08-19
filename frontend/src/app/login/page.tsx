"use client";

import { useMutation } from "@tanstack/react-query";
import {
  AudioLines,
  Bot,
  Clapperboard,
  Eye,
  EyeOff,
  ImageIcon,
  Lock,
  MessageSquare,
  Sparkles,
  User,
  Video,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { loginAction } from "@/actions/auth-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const setAuth = useUserStore((state) => state.setAuth);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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

  const featureCards = [
    {
      icon: MessageSquare,
      title: t("auth.feature1Title"),
      desc: t("auth.feature1Desc"),
      glow: "from-blue-500/20 to-cyan-500/10",
      accent: "text-blue-400",
    },
    {
      icon: ImageIcon,
      title: t("auth.feature2Title"),
      desc: t("auth.feature2Desc"),
      glow: "from-purple-500/20 to-pink-500/10",
      accent: "text-purple-400",
    },
    {
      icon: Video,
      title: t("auth.feature3Title"),
      desc: t("auth.feature3Desc"),
      glow: "from-amber-500/20 to-orange-500/10",
      accent: "text-amber-400",
    },
    {
      icon: Clapperboard,
      title: t("auth.feature4Title"),
      desc: t("auth.feature4Desc"),
      glow: "from-emerald-500/20 to-teal-500/10",
      accent: "text-emerald-400",
    },
  ];

  return (
    <main className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-background px-4 py-8 lg:p-12">
      {/* 背景动态环境光晕与点阵 */}
      <div className="pointer-events-none absolute -top-40 -left-40 size-[550px] rounded-full bg-primary/15 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 size-[550px] rounded-full bg-purple-600/15 blur-[120px]" />
      <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-40 dark:opacity-30" />

      {/* 顶部控制栏 */}
      <div className="absolute top-6 right-6 z-20 flex items-center gap-3">
        <PreferencesSwitcher />
      </div>

      <div className="relative z-10 mx-auto grid w-full max-w-6xl items-center gap-8 lg:grid-cols-12 lg:gap-12">
        {/* 左侧：全能多模态 AI 矩阵展示区 */}
        <div className="hidden flex-col justify-center space-y-6 lg:col-span-7 lg:flex">
          <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-card/60 px-3.5 py-1.5 backdrop-blur-md">
            <Sparkles className="size-4 text-primary animate-pulse" />
            <span className="text-xs font-semibold uppercase tracking-widest text-primary">
              {t("auth.heroTag")}
            </span>
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl xl:text-5xl">
              {t("auth.heroTitle")}{" "}
              <span className="gradient-text-cinema block sm:inline">
                {t("auth.heroHighlight")}
              </span>
            </h1>
            <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
              {t("auth.heroSubtitle")}
            </p>
          </div>

          {/* 4 大多模态特性卡片网格 */}
          <div className="grid grid-cols-2 gap-3.5 pt-2">
            {featureCards.map((feat, idx) => {
              const Icon = feat.icon;
              return (
                <div
                  key={idx}
                  className="group relative overflow-hidden rounded-2xl border border-border/70 bg-card/40 p-4 backdrop-blur-md transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-card/70 hover:shadow-lg hover:shadow-primary/5"
                >
                  <div
                    className={`absolute inset-0 bg-gradient-to-br ${feat.glow} opacity-0 transition-opacity duration-300 group-hover:opacity-100`}
                  />
                  <div className="relative z-10 space-y-2">
                    <div className="flex size-8 items-center justify-center rounded-lg bg-background/80 shadow-xs">
                      <Icon className={`size-4 ${feat.accent}`} />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">
                        {feat.title}
                      </h3>
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                        {feat.desc}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center gap-6 pt-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Zap className="size-3.5 text-primary" />
              主流大模型即时路由
            </span>
            <span className="flex items-center gap-1.5">
              <Bot className="size-3.5 text-purple-400" />
              上下文长记忆对话
            </span>
            <span className="flex items-center gap-1.5">
              <AudioLines className="size-3.5 text-emerald-400" />
              高保真视听合成
            </span>
          </div>
        </div>

        {/* 右侧：登录表单卡片 */}
        <div className="lg:col-span-5">
          <div className="relative overflow-hidden rounded-3xl border border-border/80 bg-card/75 p-6 shadow-2xl backdrop-blur-xl sm:p-8 dark:border-white/10 dark:shadow-black/40">
            {/* 卡片内环境发光 */}
            <div className="pointer-events-none absolute -top-24 -right-24 size-48 rounded-full bg-primary/20 blur-3xl" />

            <div className="relative z-10 space-y-6">
              {/* 头部标题与品牌 */}
              <div className="space-y-2 text-left">
                <div className="inline-flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/20">
                  <Sparkles className="size-5" />
                </div>
                <h2 className="text-2xl font-bold tracking-tight text-foreground">
                  {t("auth.loginTitle")}
                </h2>
                <p className="text-xs text-muted-foreground sm:text-sm">
                  {t("auth.loginWelcome")}
                </p>
              </div>

              {/* 登录表单 */}
              <form className="space-y-4" onSubmit={onSubmit}>
                <div className="space-y-2">
                  <Label htmlFor="username" className="text-xs font-medium">
                    {t("auth.username")}
                  </Label>
                  <div className="relative">
                    <User className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="username"
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      placeholder="admin / 您的用户名"
                      className="h-10 pl-9 pr-3 text-sm"
                      required
                      autoComplete="username"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-xs font-medium">
                    {t("auth.password")}
                  </Label>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="••••••••"
                      className="h-10 pl-9 pr-10 text-sm"
                      required
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute top-1/2 right-3 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
                    >
                      {showPassword ? (
                        <EyeOff className="size-4" />
                      ) : (
                        <Eye className="size-4" />
                      )}
                    </button>
                  </div>
                </div>

                {error ? (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs text-destructive">
                    {error}
                  </div>
                ) : null}

                <Button
                  className="h-10 w-full cursor-pointer font-semibold shadow-md transition-all active:scale-[0.99]"
                  type="submit"
                  disabled={loginMutation.isPending}
                >
                  {loginMutation.isPending ? (
                    <span className="flex items-center gap-2">
                      <span className="size-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                      {t("auth.loggingIn")}
                    </span>
                  ) : (
                    t("auth.login")
                  )}
                </Button>
              </form>

              {/* 注册跳转 */}
              <div className="flex items-center justify-between pt-2 text-xs text-muted-foreground">
                <span>{t("auth.noAccount")}</span>
                <Link
                  href="/register"
                  className="font-medium text-primary transition-colors hover:underline"
                >
                  {t("auth.goRegister")} →
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
