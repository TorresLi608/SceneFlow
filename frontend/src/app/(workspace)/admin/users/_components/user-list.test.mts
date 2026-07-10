import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node runs the TypeScript source directly with type stripping.
import { filterUsers } from "./user-list.ts";

const users = [
  { id: 1, username: "root", role: "superAdmin" as const, isDisabled: false },
  { id: 2, username: "alice", role: "user" as const, isDisabled: false },
  { id: 3, username: "bob", role: "user" as const, isDisabled: true },
];

test("filterUsers combines search, role and status filters", () => {
  assert.deepEqual(filterUsers(users, "ali", "all", "all").map((user) => user.id), [2]);
  assert.deepEqual(filterUsers(users, "", "user", "disabled").map((user) => user.id), [3]);
  assert.deepEqual(filterUsers(users, "1", "superAdmin", "active").map((user) => user.id), [1]);
});
