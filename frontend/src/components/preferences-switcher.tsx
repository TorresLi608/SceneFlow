"use client";

import { Languages, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { usePreferencesStore } from "@/store/preferences-store";

interface PreferencesSwitcherProps {
  className?: string;
}

export function PreferencesSwitcher({ className }: PreferencesSwitcherProps) {
  const { locale, t } = useI18n();
  const theme = usePreferencesStore((state) => state.theme);
  const toggleLocale = usePreferencesStore((state) => state.toggleLocale);
  const toggleTheme = usePreferencesStore((state) => state.toggleTheme);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Button variant="outline" size="sm" onClick={toggleLocale}>
        <Languages className="mr-1 size-3.5" />
        {locale === "zh" ? t("common.localeZh") : t("common.localeEn")}
      </Button>

      <Button variant="outline" size="sm" onClick={toggleTheme}>
        {theme === "dark" ? <Moon className="mr-1 size-3.5" /> : <Sun className="mr-1 size-3.5" />}
        {theme === "dark" ? t("common.themeDark") : t("common.themeLight")}
      </Button>
    </div>
  );
}
