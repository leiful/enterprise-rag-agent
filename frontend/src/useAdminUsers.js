export function useAdminUsers({
  API_BASE,
  responseError,
  refs,
  loaders,
  fetchImpl = fetch,
}) {
  const {
    isAdmin,
    usersLoading,
    usersError,
    newUserUsername,
    newUserPassword,
    newUserRole,
    newUserDepartment,
    userEdits,
    departmentsLoading,
    departmentsError,
    departments,
    newDepartmentName,
    knowledgeDepartment,
  } = refs;
  const { loadUsers, loadDepartments } = loaders;

  async function createUserAccount() {
    if (!isAdmin.value || usersLoading.value) {
      return;
    }

    const username = newUserUsername.value.trim();
    const password = newUserPassword.value;
    const role = newUserRole.value;
    const selectedDepartments = role === "admin" || !newUserDepartment.value ? [] : [newUserDepartment.value];

    if (!username || !password) {
      usersError.value = "Username and password are required.";
      return;
    }
    if (role === "user" && !newUserDepartment.value) {
      usersError.value = "Department is required for user accounts.";
      return;
    }

    usersLoading.value = true;
    usersError.value = "";

    try {
      const response = await fetchImpl(`${API_BASE}/admin/users`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ username, password, role, departments: selectedDepartments }),
      });

      if (!response.ok) {
        throw new Error(await responseError(response, `Create user failed with status ${response.status}`));
      }

      newUserUsername.value = "";
      newUserPassword.value = "";
      newUserRole.value = "user";
      newUserDepartment.value = "";
      await loadUsers();
    } catch (err) {
      usersError.value = err.message || "Create user failed";
    } finally {
      usersLoading.value = false;
    }
  }

  function userEditChanged(user) {
    const edit = userEdits.value[user.id] || {};
    const department = edit.role === "admin" ? "" : edit.department || "";
    const currentDepartment = user.role === "admin" ? "" : user.departments?.[0] || "";
    return edit.role !== user.role || department !== currentDepartment;
  }

  async function saveUserAccount(user) {
    if (!isAdmin.value || usersLoading.value) {
      return;
    }
    const edit = userEdits.value[user.id] || {};
    const role = edit.role || user.role;
    const departmentsPayload = role === "admin" || !edit.department ? [] : [edit.department];
    if (role === "user" && !edit.department) {
      usersError.value = "Department is required for user accounts.";
      return;
    }

    usersLoading.value = true;
    usersError.value = "";
    try {
      const response = await fetchImpl(`${API_BASE}/admin/users/${encodeURIComponent(user.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ role, departments: departmentsPayload }),
      });
      if (!response.ok) {
        throw new Error(await responseError(response, `Update user failed with status ${response.status}`));
      }
      await loadUsers();
    } catch (err) {
      usersError.value = err.message || "Update user failed";
    } finally {
      usersLoading.value = false;
    }
  }

  async function createDepartmentItem() {
    const name = newDepartmentName.value.trim();
    if (!name || departmentsLoading.value) {
      return;
    }

    departmentsLoading.value = true;
    departmentsError.value = "";

    try {
      const response = await fetchImpl(`${API_BASE}/admin/departments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ name }),
      });

      if (!response.ok) {
        throw new Error(await responseError(response, `Create department failed with status ${response.status}`));
      }

      newDepartmentName.value = "";
      await loadDepartments();
    } catch (err) {
      departmentsError.value = err.message || "Create department failed";
    } finally {
      departmentsLoading.value = false;
    }
  }

  async function deleteDepartmentItem(departmentId) {
    if (departmentsLoading.value) {
      return;
    }

    departmentsLoading.value = true;
    departmentsError.value = "";

    try {
      const response = await fetchImpl(`${API_BASE}/admin/departments/${encodeURIComponent(departmentId)}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(await responseError(response, `Delete department failed with status ${response.status}`));
      }

      await loadDepartments();
      if (!departments.value.some((department) => department.name === newUserDepartment.value)) {
        newUserDepartment.value = "";
      }
      if (!departments.value.some((department) => department.name === knowledgeDepartment.value)) {
        knowledgeDepartment.value = "";
      }
    } catch (err) {
      departmentsError.value = err.message || "Delete department failed";
    } finally {
      departmentsLoading.value = false;
    }
  }

  return {
    createUserAccount,
    userEditChanged,
    saveUserAccount,
    createDepartmentItem,
    deleteDepartmentItem,
  };
}
