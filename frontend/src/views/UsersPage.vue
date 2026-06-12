<script setup>
defineProps({
  usersTab: { type: String, required: true },
  setUsersTab: { type: Function, required: true },
  newUserUsername: { type: String, required: true },
  newUserPassword: { type: String, required: true },
  newUserRole: { type: String, required: true },
  newUserDepartment: { type: String, required: true },
  departments: { type: Array, required: true },
  usersLoading: { type: Boolean, required: true },
  usersError: { type: String, default: "" },
  users: { type: Array, required: true },
  userEdits: { type: Object, required: true },
  departmentsLoading: { type: Boolean, required: true },
  departmentsError: { type: String, default: "" },
  newDepartmentName: { type: String, required: true },
  createUserAccount: { type: Function, required: true },
  userEditChanged: { type: Function, required: true },
  saveUserAccount: { type: Function, required: true },
  createDepartmentItem: { type: Function, required: true },
  deleteDepartmentItem: { type: Function, required: true },
  formatDate: { type: Function, required: true },
  formatDepartments: { type: Function, required: true },
});

const emit = defineEmits([
  "update:newUserUsername",
  "update:newUserPassword",
  "update:newUserRole",
  "update:newUserDepartment",
  "update:newDepartmentName",
]);
</script>

<template>
  <div class="users-column">
          <section class="users-section">
            <div class="section-header">
              <div>
                <h2>{{ usersTab === "departments" ? "Departments" : "Users" }}</h2>
                <p>
                  {{
                    usersTab === "departments"
                      ? "Maintain the department options used by users and knowledge files."
                      : "Create accounts and choose who can manage the workspace."
                  }}
                </p>
              </div>
            </div>

            <div class="operations-tabs" role="tablist" aria-label="User management sections">
              <button
                type="button"
                :class="{ active: usersTab === 'users' }"
                @click="setUsersTab('users')"
              >
                Users
              </button>
              <button
                type="button"
                :class="{ active: usersTab === 'departments' }"
                @click="setUsersTab('departments')"
              >
                Departments
              </button>
            </div>

            <template v-if="usersTab === 'users'">
            <form class="user-form" @submit.prevent="createUserAccount">
              <label>
                <span>Username</span>
                <input :value="newUserUsername" @input="emit('update:newUserUsername', $event.target.value)" autocomplete="off" placeholder="employee.name" />
              </label>
              <label>
                <span>Password</span>
                <input
                  :value="newUserPassword" @input="emit('update:newUserPassword', $event.target.value)"
                  type="password"
                  autocomplete="new-password"
                  placeholder="At least 12 characters"
                />
              </label>
              <label>
                <span>Role</span>
                <select :value="newUserRole" @change="emit('update:newUserRole', $event.target.value)">
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </label>
              <label>
                <span>Departments</span>
                <select
                  :value="newUserDepartment" @change="emit('update:newUserDepartment', $event.target.value)"
                  :disabled="newUserRole === 'admin'"
                >
                  <option value="">
                    {{ newUserRole === "admin" ? "All departments" : "Select department" }}
                  </option>
                  <option
                    v-for="department in departments"
                    :key="department.id"
                    :value="department.name"
                  >
                    {{ department.name }}
                  </option>
                </select>
              </label>
              <button
                type="submit"
                :disabled="usersLoading || !newUserUsername.trim() || !newUserPassword || (newUserRole === 'user' && !newUserDepartment)"
              >
                {{ usersLoading ? "Creating" : "Create" }}
              </button>
            </form>

            <p v-if="usersError" class="error users-error">{{ usersError }}</p>

            <div class="user-list">
              <article v-for="user in users" :key="user.id" class="user-item">
                <div>
                  <h3>{{ user.username }}</h3>
                  <p>{{ user.created_at ? formatDate(user.created_at) : "Created" }}</p>
                  <p class="user-departments">
                    {{ user.role === "admin" ? "All departments" : formatDepartments(user.departments) }}
                  </p>
                </div>
                <div v-if="userEdits[user.id]" class="user-edit-controls">
                  <select v-model="userEdits[user.id].role">
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                  <select
                    v-model="userEdits[user.id].department"
                    :disabled="userEdits[user.id].role === 'admin'"
                  >
                    <option value="">
                      {{ userEdits[user.id].role === "admin" ? "All departments" : "Select department" }}
                    </option>
                    <option
                      v-for="department in departments"
                      :key="department.id"
                      :value="department.name"
                    >
                      {{ department.name }}
                    </option>
                  </select>
                  <button
                    class="secondary-button"
                    type="button"
                    :disabled="usersLoading || !userEditChanged(user)"
                    @click="saveUserAccount(user)"
                  >
                    Save
                  </button>
                </div>
              </article>

              <p v-if="users.length === 0 && !usersLoading" class="empty-state">
                No users found.
              </p>
            </div>
            </template>

            <template v-else>
            <form class="department-form" @submit.prevent="createDepartmentItem">
              <label>
                <span>Name</span>
                <input
                  :value="newDepartmentName" @input="emit('update:newDepartmentName', $event.target.value)"
                  autocomplete="off"
                  placeholder="Finance"
                />
              </label>
              <button
                type="submit"
                :disabled="departmentsLoading || !newDepartmentName.trim()"
              >
                {{ departmentsLoading ? "Saving" : "Add" }}
              </button>
            </form>

            <p v-if="departmentsError" class="error users-error">{{ departmentsError }}</p>

            <div class="department-list">
              <article
                v-for="department in departments"
                :key="department.id"
                class="department-item"
              >
                <div>
                  <h3>{{ department.name }}</h3>
                  <p>{{ department.created_at ? formatDate(department.created_at) : "Created" }}</p>
                </div>
                <button
                  class="danger-button"
                  type="button"
                  :disabled="departmentsLoading"
                  @click="deleteDepartmentItem(department.id)"
                >
                  Delete
                </button>
              </article>

              <p v-if="departments.length === 0 && !departmentsLoading" class="empty-state">
                No departments yet.
              </p>
            </div>
            </template>

          </section>
        </div>
</template>
