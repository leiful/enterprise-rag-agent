import test from "node:test";
import assert from "node:assert/strict";

import { useAdminUsers } from "../useAdminUsers.js";

function ref(value) {
  return { value };
}

function createSubject(overrides = {}) {
  const calls = [];
  const refs = {
    isAdmin: ref(true),
    usersLoading: ref(false),
    usersError: ref(""),
    newUserUsername: ref(""),
    newUserPassword: ref(""),
    newUserRole: ref("user"),
    newUserDepartment: ref(""),
    userEdits: ref({}),
    departmentsLoading: ref(false),
    departmentsError: ref(""),
    departments: ref([]),
    newDepartmentName: ref(""),
    knowledgeDepartment: ref(""),
    ...overrides.refs,
  };
  const loaders = {
    loadUsers: async () => calls.push("users"),
    loadDepartments: async () => calls.push("departments"),
    ...overrides.loaders,
  };
  const subject = useAdminUsers({
    API_BASE: "http://api.test",
    responseError: async (response, fallback) => `${fallback}: ${response.status}`,
    refs,
    loaders,
    fetchImpl: overrides.fetchImpl || (async () => ({ ok: true, json: async () => ({}) })),
  });
  return { calls, refs, subject };
}

test("userEditChanged detects role or department changes", () => {
  const { refs, subject } = createSubject({
    refs: {
      userEdits: ref({
        7: { role: "user", department: "Finance" },
      }),
    },
  });
  const user = { id: 7, role: "user", departments: ["HR"] };

  assert.equal(subject.userEditChanged(user), true);

  refs.userEdits.value[7].department = "HR";
  assert.equal(subject.userEditChanged(user), false);
});

test("createUserAccount requires a department for user accounts", async () => {
  const { refs, subject } = createSubject({
    refs: {
      newUserUsername: ref("alice"),
      newUserPassword: ref("strong-password"),
      newUserRole: ref("user"),
      newUserDepartment: ref(""),
    },
  });

  await subject.createUserAccount();

  assert.equal(refs.usersError.value, "Department is required for user accounts.");
});

test("createUserAccount posts selected user fields and clears the form", async () => {
  let requestBody = null;
  const { refs, calls, subject } = createSubject({
    refs: {
      newUserUsername: ref(" alice "),
      newUserPassword: ref("strong-password"),
      newUserRole: ref("user"),
      newUserDepartment: ref("HR"),
    },
    fetchImpl: async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return { ok: true, json: async () => ({}) };
    },
  });

  await subject.createUserAccount();

  assert.deepEqual(requestBody, {
    username: "alice",
    password: "strong-password",
    role: "user",
    departments: ["HR"],
  });
  assert.equal(refs.newUserUsername.value, "");
  assert.equal(refs.newUserPassword.value, "");
  assert.equal(refs.newUserRole.value, "user");
  assert.equal(refs.newUserDepartment.value, "");
  assert.deepEqual(calls, ["users"]);
});

test("deleteDepartmentItem clears department selections that no longer exist", async () => {
  const { refs, calls, subject } = createSubject({
    refs: {
      departments: ref([{ name: "Finance" }]),
      newUserDepartment: ref("HR"),
      knowledgeDepartment: ref("HR"),
    },
  });

  await subject.deleteDepartmentItem(3);

  assert.equal(refs.newUserDepartment.value, "");
  assert.equal(refs.knowledgeDepartment.value, "");
  assert.deepEqual(calls, ["departments"]);
});
