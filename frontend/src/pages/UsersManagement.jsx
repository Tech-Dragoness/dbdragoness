import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import Sidebar from "../components/Sidebar";

function UsersManagement() {
  const { dbName } = useParams();
  const navigate = useNavigate();

  const [users, setUsers] = useState([]);
  const [supportsUsers, setSupportsUsers] = useState(false);
  const [dbType, setDbType] = useState("sql");
  const [handlerName, setHandlerName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  const [createForm, setCreateForm] = useState({
    username: "",
    password: "",
    privileges: [],
  });

  const [editForm, setEditForm] = useState({
    username: "",
    password: "",
    privileges: [],
  });

  useEffect(() => {
    fetchUsers();
  }, [dbName]);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/db/${dbName}/users`);

      if (response.data.success) {
        setUsers(response.data.users || []);
        setSupportsUsers(response.data.supports_users);
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);
      } else {
        setError(response.data.error || "Failed to fetch users");
      }
    } catch (err) {
      console.error("Failed to fetch users:", err);
      setError("Failed to connect to server");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    try {
      const response = await axios.post(
        `/api/db/${dbName}/users/create`,
        createForm
      );

      if (response.data.success) {
        setMessage(response.data.message);
        setShowCreateModal(false);
        setCreateForm({ username: "", password: "", privileges: [] });
        fetchUsers();
      } else {
        setError(response.data.error || "Failed to create user");
      }
    } catch (err) {
      setError(
        "Failed to create user: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleUpdateUser = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    try {
      const response = await axios.post(
        `/api/db/${dbName}/users/update`,
        editForm
      );

      if (response.data.success) {
        setMessage(response.data.message);
        setShowEditModal(false);
        setEditForm({ username: "", password: "", privileges: [] });
        setEditingUser(null);
        fetchUsers();
      } else {
        setError(response.data.error || "Failed to update user");
      }
    } catch (err) {
      setError(
        "Failed to update user: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleDeleteUser = async (username) => {
    if (!window.confirm(`Delete user ${username}? This cannot be undone!`)) {
      return;
    }

    try {
      const response = await axios.post(`/api/db/${dbName}/users/delete`, {
        username,
      });

      if (response.data.success) {
        setMessage(response.data.message);
        fetchUsers();
      } else {
        setError(response.data.error || "Failed to delete user");
      }
    } catch (err) {
      setError(
        "Failed to delete user: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const openEditModal = async (username) => {
    try {
      const response = await axios.get(
        `/api/db/${dbName}/users/${username}/privileges`
      );

      if (response.data.success) {
        setEditForm({
          username: username,
          password: "",
          privileges: response.data.privileges || [],
        });
        setEditingUser(username);
        setShowEditModal(true);
      } else {
        setError("Failed to load user data");
      }
    } catch (err) {
      setError("Failed to load user data: " + err.message);
    }
  };

  const viewConnectionInfo = async (username) => {
    try {
      const response = await axios.get(
        `/api/db/${dbName}/users/${username}/connection`
      );

      if (response.data.success) {
        // Create modal with connection info
        const modal = document.createElement("div");
        modal.style.cssText =
          "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;";

        modal.innerHTML = `
          <div style="background:white;padding:30px;border-radius:15px;max-width:900px;width:100%;max-height:90%;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,0.3);">
            <h2 style="margin:0 0 20px 0;color:#4b0082;">🔗 Connection Info for ${username}</h2>
            
            <div style="margin-bottom:20px;">
              <strong style="display:block;margin-bottom:10px;">Connection String:</strong>
              <code style="display:block;background:#2d2d2d;color:#f8f8f2;padding:15px;border-radius:8px;overflow-x:auto;">${escapeHtml(
                response.data.connection_string
              )}</code>
            </div>
            
            <div style="margin-bottom:20px;">
              <strong style="display:block;margin-bottom:10px;">Test Code:</strong>
              <pre id="test-code" style="background:#2d2d2d;color:#f8f8f2;padding:20px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.6;">${escapeHtml(
                response.data.test_code
              )}</pre>
            </div>
            
            ${
              response.data.notes && response.data.notes.length > 0
                ? `
            <div style="background:#fff3cd;border-left:3px solid #ffc107;padding:15px;border-radius:8px;margin-bottom:20px;color:black;">
              <strong>💡 Tips:</strong>
              <ul style="margin:5px 0;padding-left:20px;color:black;">
                ${response.data.notes
                  .map((note) => `<li>${note}</li>`)
                  .join("")}
              </ul>
            </div>
            `
                : ""
            }
            
            <div style="display:flex;gap:10px;justify-content:flex-end;">
              <button onclick="copyTestCode(event)" 
                style="padding:10px 20px;background:#6a5acd;color:white;border:none;border-radius:8px;cursor:pointer;">
                📋 Copy Code
              </button>
              <button onclick="this.closest('div[style*=fixed]').remove()" 
                style="padding:10px 20px;background:#6c757d;color:white;border:none;border-radius:8px;cursor:pointer;">
                Close
              </button>
            </div>
          </div>
        `;

        document.body.appendChild(modal);

        // Add copy function
        window.copyTestCode = (event) => {
          const code = document.getElementById("test-code").textContent;
          navigator.clipboard
            .writeText(code)
            .then(() => {
              const btn = event.target;
              const originalText = btn.textContent;
              btn.textContent = "✅ Copied!";
              btn.style.background = "#4caf50";
              setTimeout(() => {
                btn.textContent = originalText;
                btn.style.background = "#6a5acd";
              }, 2000);
            })
            .catch((err) => {
              alert("Failed to copy: " + err);
            });
        };
      } else {
        alert("Failed to load connection info: " + response.data.error);
      }
    } catch (err) {
      alert("Error: " + err.message);
    }
  };

  const escapeHtml = (text) => {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  };

  const togglePrivilege = (form, setForm, privilege) => {
    setForm((prev) => ({
      ...prev,
      privileges: prev.privileges.includes(privilege)
        ? prev.privileges.filter((p) => p !== privilege)
        : [...prev.privileges, privilege],
    }));
  };

  const handleAllPrivilegesChange = (form, setForm, checked) => {
    if (checked) {
      setForm((prev) => ({
        ...prev,
        privileges: [
          "SELECT",
          "INSERT",
          "UPDATE",
          "DELETE",
          "CREATE",
          "DROP",
          "ALL",
        ],
      }));
    } else {
      setForm((prev) => ({ ...prev, privileges: [] }));
    }
  };

  if (loading) {
    return (
      <>
        <Sidebar dbType={dbType} handlerName={handlerName} />
        <div className="center">
          <div className="loading">Loading users...</div>
        </div>
      </>
    );
  }

  if (!supportsUsers) {
    return (
      <>
        <Sidebar dbType={dbType} handlerName={handlerName} />
        <div className="center">
          <h2 style={{ color: "#f0f0f0" }}>👥 User Management</h2>
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              navigate(`/db/${dbName}`);
            }}
            style={{ color: "#bb86fc" }}
          >
            ← Back to Database
          </a>
          <br />
          <br />
          <div
            style={{
              textAlign: "center",
              padding: "40px",
              background: "#f8f8f8",
              borderRadius: "10px",
              margin: "20px auto",
              maxWidth: "600px",
            }}
          >
            <p style={{ fontSize: "3em", margin: 0 }}>⚠️</p>
            <h3 style={{ color: "#666" }}>User Management Not Supported</h3>
            <p style={{ color: "#999" }}>
              This database type does not support user management.
            </p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Sidebar dbType={dbType} handlerName={handlerName} />
      <div className="center">
        <h2 style={{ color: "#f0f0f0" }}>👥 User Management for {dbName}</h2>
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/db/${dbName}`);
          }}
          style={{ color: "#bb86fc" }}
        >
          ← Back to Database
        </a>
        <br />
        <br />

        {error && <div className="error">{error}</div>}
        {message && <div className="success">{message}</div>}

        <button
          onClick={() => setShowCreateModal(true)}
          style={{
            padding: "12px 24px",
            background: "linear-gradient(135deg, #4caf50, #2e7d32)",
            color: "white",
            border: "none",
            borderRadius: "8px",
            fontWeight: "bold",
            cursor: "pointer",
            marginBottom: "20px",
          }}
        >
          ➕ Create New User
        </button>

        <button
          onClick={async () => {
            if (
              !window.confirm(
                `Sign out from ${handlerName}?\n\nYou will need to re-enter credentials to access ${handlerName} again.`
              )
            )
              return;

            try {
              const res = await axios.post("/api/sign_out", {
                handler_name: handlerName,
              });

              if (res.data.success) {
                alert("Signed out successfully");
                navigate("/");
              } else {
                alert("Sign out failed: " + res.data.error);
              }
            } catch (err) {
              alert("Sign out failed");
            }
          }}
          style={{
            padding: "10px 18px",
            background: "#ff6b6b",
            color: "white",
            border: "none",
            borderRadius: "8px",
            fontWeight: "bold",
            cursor: "pointer",
            boxShadow: "0 4px 15px rgba(255, 107, 107, 0.4)",
          }}
        >
          Sign Out ({handlerName})
        </button>

        {users.length > 0 ? (
          <table
            className="result-table"
            style={{ width: "95%", margin: "20px auto" }}
          >
            <thead>
              <tr>
                <th>Username</th>
                <th>Has Password</th>
                <th>Privileges</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user, idx) => (
                <tr key={idx}>
                  <td>
                    <strong>{user.username}</strong>
                  </td>
                  <td>
                    {user.has_password ? (
                      <span style={{ color: "#4caf50" }}>✓ Yes</span>
                    ) : (
                      <span style={{ color: "#999" }}>✗ No</span>
                    )}
                  </td>
                  <td>
                    <div
                      style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}
                    >
                      {user.privileges.map((priv, pidx) => (
                        <span
                          key={pidx}
                          style={{
                            background: "#e3f2fd",
                            color: "#1976d2",
                            padding: "4px 8px",
                            borderRadius: "12px",
                            fontSize: "12px",
                            fontWeight: "600",
                          }}
                        >
                          {priv}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <button
                      onClick={() => viewConnectionInfo(user.username)}
                      style={{
                        background: "#6a5acd",
                        color: "white",
                        padding: "6px 12px",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer",
                        marginRight: "5px",
                      }}
                    >
                      🔗 Connection
                    </button>
                    <button
                      onClick={() => openEditModal(user.username)}
                      style={{
                        background: "#ff9800",
                        color: "white",
                        padding: "6px 12px",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer",
                        marginRight: "5px",
                      }}
                    >
                      ✏️ Edit
                    </button>
                    <button
                      onClick={() => handleDeleteUser(user.username)}
                      style={{
                        background: "#dc3545",
                        color: "white",
                        padding: "6px 12px",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer",
                      }}
                    >
                      🗑️ Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div
            style={{
              textAlign: "center",
              padding: "40px",
              background: "#f8f8f8",
              borderRadius: "10px",
              margin: "20px auto",
              maxWidth: "600px",
            }}
          >
            <p style={{ fontSize: "3em", margin: 0 }}>👤</p>
            <h3 style={{ color: "#666" }}>No Users Found</h3>
            <p style={{ color: "#999" }}>
              Create your first user to get started.
            </p>
          </div>
        )}

        {/* Create User Modal */}
        {showCreateModal && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              background: "rgba(0,0,0,0.7)",
              zIndex: 9999,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            onClick={() => setShowCreateModal(false)}
          >
            <div
              style={{
                background: "white",
                padding: "30px",
                borderRadius: "15px",
                maxWidth: "600px",
                width: "90%",
                maxHeight: "90vh",
                overflowY: "auto",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 style={{ marginTop: 0, color: "#4b0082" }}>
                ➕ Create New User
              </h3>
              <form onSubmit={handleCreateUser}>
                <div style={{ marginBottom: "15px" }}>
                  <label
                    style={{
                      display: "block",
                      fontWeight: "bold",
                      marginBottom: "5px",
                      color: "#333",
                    }}
                  >
                    Username:
                  </label>
                  <input
                    type="text"
                    value={createForm.username}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, username: e.target.value })
                    }
                    required
                    style={{
                      width: "100%",
                      padding: "10px",
                      border: "2px solid #9370db",
                      borderRadius: "8px",
                      fontSize: "15px",
                    }}
                  />
                </div>
                <div style={{ marginBottom: "15px" }}>
                  <label
                    style={{
                      display: "block",
                      fontWeight: "bold",
                      marginBottom: "5px",
                      color: "#333",
                    }}
                  >
                    Password (optional for some databases):
                  </label>
                  <input
                    type="password"
                    value={createForm.password}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, password: e.target.value })
                    }
                    style={{
                      width: "100%",
                      padding: "10px",
                      border: "2px solid #9370db",
                      borderRadius: "8px",
                      fontSize: "15px",
                    }}
                  />
                </div>
                <div style={{ marginBottom: "20px" }}>
                  <label
                    style={{
                      display: "block",
                      fontWeight: "bold",
                      marginBottom: "10px",
                      color: "#333",
                    }}
                  >
                    Privileges:
                  </label>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "10px",
                    }}
                  >
                    {[
                      "SELECT",
                      "INSERT",
                      "UPDATE",
                      "DELETE",
                      "CREATE",
                      "DROP",
                    ].map((priv) => (
                      <label
                        key={priv}
                        style={{ cursor: "pointer", color: "#333" }}
                      >
                        <input
                          type="checkbox"
                          checked={createForm.privileges.includes(priv)}
                          onChange={() =>
                            togglePrivilege(createForm, setCreateForm, priv)
                          }
                        />{" "}
                        {priv}
                      </label>
                    ))}
                    <label
                      style={{
                        cursor: "pointer",
                        color: "#333",
                        gridColumn: "1 / -1",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={createForm.privileges.includes("ALL")}
                        onChange={(e) =>
                          handleAllPrivilegesChange(
                            createForm,
                            setCreateForm,
                            e.target.checked
                          )
                        }
                      />{" "}
                      ALL PRIVILEGES
                    </label>
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "10px",
                    justifyContent: "flex-end",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    style={{
                      padding: "10px 20px",
                      background: "#6c757d",
                      color: "white",
                      border: "none",
                      borderRadius: "8px",
                      cursor: "pointer",
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    style={{
                      padding: "10px 20px",
                      background: "#4caf50",
                      color: "white",
                      border: "none",
                      borderRadius: "8px",
                      cursor: "pointer",
                      fontWeight: "bold",
                    }}
                  >
                    Create User
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Edit User Modal */}
        {showEditModal && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              background: "rgba(0,0,0,0.7)",
              zIndex: 9999,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            onClick={() => setShowEditModal(false)}
          >
            <div
              style={{
                background: "white",
                padding: "30px",
                borderRadius: "15px",
                maxWidth: "600px",
                width: "90%",
                maxHeight: "90vh",
                overflowY: "auto",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 style={{ marginTop: 0, color: "#4b0082" }}>✏️ Edit User</h3>
              <form onSubmit={handleUpdateUser}>
                <div style={{ marginBottom: "15px" }}>
                  <label
                    style={{
                      display: "block",
                      fontWeight: "bold",
                      marginBottom: "5px",
                      color: "#333",
                    }}
                  >
                    Username:
                  </label>
                  <input
                    type="text"
                    value={editForm.username}
                    disabled
                    style={{
                      width: "100%",
                      padding: "10px",
                      border: "2px solid #ddd",
                      borderRadius: "8px",
                      fontSize: "15px",
                      background: "#f5f5f5",
                    }}
                  />
                </div>
                <div style={{ marginBottom: "15px" }}>
                  <label
                    style={{
                      display: "block",
                      fontWeight: "bold",
                      marginBottom: "5px",
                      color: "#333",
                    }}
                  >
                    New Password (leave empty to keep current):
                  </label>
                  <input
                    type="password"
                    value={editForm.password}
                    onChange={(e) =>
                      setEditForm({ ...editForm, password: e.target.value })
                    }
                    style={{
                      width: "100%",
                      padding: "10px",
                      border: "2px solid #9370db",
                      borderRadius: "8px",
                      fontSize: "15px",
                    }}
                  />
                </div>
                <div style={{ marginBottom: "20px" }}>
                  <label
                    style={{
                      display: "block",
                      fontWeight: "bold",
                      marginBottom: "10px",
                      color: "#333",
                    }}
                  >
                    Privileges:
                  </label>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "10px",
                    }}
                  >
                    {[
                      "SELECT",
                      "INSERT",
                      "UPDATE",
                      "DELETE",
                      "CREATE",
                      "DROP",
                    ].map((priv) => (
                      <label
                        key={priv}
                        style={{ cursor: "pointer", color: "#333" }}
                      >
                        <input
                          type="checkbox"
                          checked={editForm.privileges.includes(priv)}
                          onChange={() =>
                            togglePrivilege(editForm, setEditForm, priv)
                          }
                        />{" "}
                        {priv}
                      </label>
                    ))}
                    <label
                      style={{
                        cursor: "pointer",
                        color: "#333",
                        gridColumn: "1 / -1",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={editForm.privileges.includes("ALL")}
                        onChange={(e) =>
                          handleAllPrivilegesChange(
                            editForm,
                            setEditForm,
                            e.target.checked
                          )
                        }
                      />{" "}
                      ALL PRIVILEGES
                    </label>
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "10px",
                    justifyContent: "flex-end",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setShowEditModal(false)}
                    style={{
                      padding: "10px 20px",
                      background: "#6c757d",
                      color: "white",
                      border: "none",
                      borderRadius: "8px",
                      cursor: "pointer",
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    style={{
                      padding: "10px 20px",
                      background: "#ff9800",
                      color: "white",
                      border: "none",
                      borderRadius: "8px",
                      cursor: "pointer",
                      fontWeight: "bold",
                    }}
                  >
                    Update User
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

export default UsersManagement;
