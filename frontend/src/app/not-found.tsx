"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, FileQuestion, Home } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

export default function NotFound() {
  const router = useRouter();
  const { t } = useI18n();

  const handleBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/");
    }
  };

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-background p-4 text-foreground selection:bg-primary/20">
      <div className="flex max-w-md flex-col items-center text-center">
        <div className="flex size-16 items-center justify-center rounded-2xl border border-border/80 bg-muted/40 text-primary shadow-lg backdrop-blur-md">
          <FileQuestion className="size-8" />
        </div>
        <h1 className="mt-6 text-5xl font-black tracking-tight text-foreground/90 font-mono">404</h1>
        <h2 className="mt-2 text-lg font-bold text-foreground">{t("notFound.title")}</h2>
        <p className="mt-2 text-xs sm:text-sm text-muted-foreground leading-relaxed max-w-sm">
          {t("notFound.description")}
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleBack}
            className="cursor-pointer gap-2"
          >
            <ArrowLeft className="size-3.5" />
            {t("notFound.backPrevious")}
          </Button>
          <Button
            size="sm"
            className="cursor-pointer gap-2"
            render={<Link href="/" />}
          >
            <Home className="size-3.5" />
            {t("notFound.backHome")}
          </Button>
        </div>
      </div>
    </main>
  );
}

