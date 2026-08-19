"use client";

import { useMutation } from "@tanstack/react-query";
import {
  AudioLines,
  Bot,
  Clapperboard,
  Eye,
  EyeOff,
  ImageIcon,
  KeyRound,
  Lock,
  MessageSquare,
  Sparkles,
  User,
  UserCheck,
  Video,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { registerAction } from "@/actions/auth-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useI18n();
  const setAuth = useUserStore((state) => state.setAuth);

  const initialCode = searchParams.get("code") || searchParams.get("invitationCode") || "";
  const [username, setUsername] = useState("");
  const [nickname, setNickname] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [invitationCode, setInvitationCode] = useState(initialCode.toUpperCase());
  const [error, setError] = useState<string | null>(null);

  const registerMutation = useMutation({
    mutationFn: registerAction,
    onSuccess: (data) => {
      setAuth(data.token, data.user);
      router.replace("/");
    },
    onError: (requestError) => {
      setError(resolveRequestError(requestError, t("auth.registerFailed")));
    },
  });

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (password !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return;
    }

    setError(null);

    registerMutation.mutate({
      username,
      nickname: nickname.trim(),
      password,
      invitationCode,
    });
  };

  return (
    <form className="space-y-3.5" onSubmit={onSubmit}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="username" className="text-xs font-medium">
            {t("auth.username")}
          </Label>
          <div className="relative">
            <User className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="your_name"
              className="h-9 pl-9 pr-3 text-xs sm:text-sm"
              required
              autoComplete="username"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="nickname" className="text-xs font-medium">
            {t("auth.nickname")}
          </Label>
          <div className="relative">
            <UserCheck className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="nickname"
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
              maxLength={64}
              placeholder="显示昵称"
              className="h-9 pl-9 pr-3 text-xs sm:text-sm"
            />
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
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
            className="h-9 pl-9 pr-10 text-xs sm:text-sm"
            required
            autoComplete="new-password"
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

      <div className="space-y-1.5">
        <Label htmlFor="confirmPassword" className="text-xs font-medium">
          {t("auth.confirmPassword")}
        </Label>
        <div className="relative">
          <Lock className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="confirmPassword"
            type={showPassword ? "text" : "password"}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            placeholder="••••••••"
            className="h-9 pl-9 pr-3 text-xs sm:text-sm"
            required
            autoComplete="new-password"
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="invitationCode" className="text-xs font-medium">
          {t("auth.invitationCode")}
        </Label>
        <div className="relative">
          <KeyRound className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="invitationCode"
            value={invitationCode}
            onChange={(event) => setInvitationCode(event.target.value.toUpperCase())}
            placeholder="INVITE-XXXX"
            className="h-9 pl-9 pr-3 uppercase tracking-wider text-xs sm:text-sm"
            required
          />
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2 text-xs text-destructive">
          {error}
        </div>
      ) : null}

      <Button
        className="h-10 w-full cursor-pointer font-semibold shadow-md transition-all active:scale-[0.99]"
        type="submit"
        disabled={registerMutation.isPending}
      >
        {registerMutation.isPending ? (
          <span className="flex items-center gap-2">
            <span className="size-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
            {t("auth.registering")}
          </span>
        ) : (
          t("auth.register")
        )}
      </Button>
    </form>
  );
}

export default function RegisterPage() {
  const { t } = useI18n();

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
    <main className="relative flex min-h-screen w-full items-center justify-center overflow-x-hidden bg-background px-4 py-8 sm:px-6 lg:px-8">
      {/* 顶部工具条 */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-2 sm:top-6 sm:right-6">
        <PreferencesSwitcher />
      </div>

      {/* 背景光晕装饰 */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-[25%] -left-[10%] size-[600px] rounded-full bg-primary/10 blur-[130px]" />
        <div className="absolute -bottom-[20%] -right-[10%] size-[600px] rounded-full bg-cyan-500/10 blur-[140px]" />
        <div className="absolute top-1/2 left-1/2 size-[400px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-purple-500/5 blur-[120px]" />
        <div className="absolute inset-0 bg-grid-dots opacity-40" />
      </div>

      <div className="relative z-10 grid w-full max-w-5xl grid-cols-1 items-center gap-8 lg:grid-cols-12 lg:gap-12">
        {/* 左侧：品牌矩阵与多模态特性展示 */}
        <div className="hidden flex-col justify-center space-y-6 lg:col-span-7 lg:flex">
          {/* 品牌 Badge */}
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary backdrop-blur-md">
              <Sparkles className="size-3.5 animate-pulse" />
              SceneFlow AI Studio
            </span>
            <span className="text-xs text-muted-foreground">
              全能型多模态 AI 创作工作台
            </span>
          </div>

          {/* 核心标语 */}
          <div className="space-y-2 text-left">
            <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              <span className="gradient-text-cinema">释放无限创意潜能</span>
              <br />
              <span className="text-foreground">一站式多模态生产力中枢</span>
            </h1>
            <p className="max-w-lg text-sm text-muted-foreground leading-relaxed">
              集智能问答、图像设计、动态视频、声音合成与短剧/漫剧工坊于一体。从灵感发散到工业级资产交付，全流程由先进 AI 引擎驱动。
            </p>
          </div>

          {/* 4 大核心特性卡片矩阵 */}
          <div className="grid grid-cols-2 gap-3.5 pt-2">
            {featureCards.map((feat, idx) => {
              const Icon = feat.icon;
              return (
                <div
                  key={idx}
                  className="group relative overflow-hidden rounded-2xl border border-border/70 bg-card/60 p-4 text-left shadow-xs backdrop-blur-md transition-all duration-300 hover:-translate-y-0.5 hover:border-border hover:shadow-md"
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

        {/* 右侧：注册表单卡片 */}
        <div className="lg:col-span-5">
          <div className="relative overflow-hidden rounded-3xl border border-border/80 bg-card/75 p-6 shadow-2xl backdrop-blur-xl sm:p-8 dark:border-white/10 dark:shadow-black/40">
            {/* 卡片内环境发光 */}
            <div className="pointer-events-none absolute -top-24 -right-24 size-48 rounded-full bg-primary/20 blur-3xl" />

            <div className="relative z-10 space-y-5">
              {/* 头部标题与品牌 */}
              <div className="space-y-1.5 text-left">
                <div className="inline-flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/20">
                  <Sparkles className="size-5" />
                </div>
                <h2 className="text-2xl font-bold tracking-tight text-foreground">
                  {t("auth.registerTitle")}
                </h2>
                <p className="text-xs text-muted-foreground sm:text-sm">
                  {t("auth.registerWelcome")}
                </p>
              </div>

              {/* 注册表单 */}
              <Suspense fallback={<div className="h-64 flex items-center justify-center text-xs text-muted-foreground">加载中...</div>}>
                <RegisterForm />
              </Suspense>

              {/* 登录跳转 */}
              <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground">
                <span>{t("auth.hasAccount")}</span>
                <Link
                  href="/login"
                  className="font-medium text-primary transition-colors hover:underline"
                >
                  {t("auth.goLogin")} →
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
