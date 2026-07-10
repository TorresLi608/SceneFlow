export type UserRoleFilter = "all" | "user" | "superAdmin";
export type UserStatusFilter = "all" | "active" | "disabled";

interface UserListItem {
  id: number;
  username: string;
  role: "user" | "superAdmin";
  isDisabled: boolean;
}

export function filterUsers<T extends UserListItem>(
  users: T[],
  search: string,
  roleFilter: UserRoleFilter,
  statusFilter: UserStatusFilter
) {
  const query = search.trim().toLowerCase();
  return users.filter((user) => {
    const matchesSearch = !query || user.username.toLowerCase().includes(query) || String(user.id).includes(query);
    const matchesRole = roleFilter === "all" || user.role === roleFilter;
    const matchesStatus =
      statusFilter === "all" || (statusFilter === "disabled" ? user.isDisabled : !user.isDisabled);
    return matchesSearch && matchesRole && matchesStatus;
  });
}
