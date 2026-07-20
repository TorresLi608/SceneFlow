"use client";

import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

import { InvitationCodeManager } from "./_components/invitation-code-manager";

export default function InvitationCodesPage() {
  const { t } = useI18n();
  const user = useUserStore((state) => state.user);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      {user?.role === "superAdmin" ? (
        <InvitationCodeManager />
      ) : (
        <p className="text-sm text-muted-foreground">{user ? t("home.noInvitationCodeManagementPermission") : t("common.loading")}</p>
      )}
    </div>
  );
}
