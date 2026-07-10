"use client";

import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

import { AdminUsersManager } from "./_components/admin-users-manager";

export default function AdminUsersPage() {
  const { t } = useI18n();
  const user = useUserStore((state) => state.user);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      {user?.role === "superAdmin" ? (
        <AdminUsersManager />
      ) : (
        <p className="text-sm text-muted-foreground">
          {user ? t("home.noUserManagementPermission") : t("common.loading")}
        </p>
      )}
    </div>
  );
}
