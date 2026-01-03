import React, { useState } from "react";
import axios from "axios";

function RenameDatabaseModal({ dbName, onClose, onSuccess }) {
  const [newName, setNewName] = useState(dbName + "_copy");
  const [keepOld, setKeepOld] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRename = async (e) => {
    e.preventDefault();
    setError("");

    if (!newName.match(/^[a-zA-Z][a-zA-Z0-9_]*$/)) {
      setError(
        "Database name must start with a letter, contain only letters, numbers, underscores."
      );
      return;
    }

    if (newName === dbName) {
      setError("New name must be different from current name.");
      return;
    }

    setLoading(true);

    try {
      const response = await axios.post("/api/databases/rename", {
        old_name: dbName,
        new_name: newName,
        keep_old: keepOld,
      });

      if (response.data.success) {
        onSuccess(newName);
        onClose();
      } else {
        setError(response.data.error || "Failed to rename database");
      }
    } catch (err) {
      console.error("Rename error:", err);
      setError(err.response?.data?.error || "Failed to rename database");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        background: "rgba(0, 0, 0, 0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1e0033, #3a0066)",
          padding: "30px",
          borderRadius: "15px",
          maxWidth: "500px",
          width: "95%",
          border: "2px solid #9370db",
          boxShadow: "0 10px 40px rgba(147, 112, 219, 0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ color: "#f0f0f0", marginBottom: "20px" }}>
          Rename Database
        </h2>

        {error && (
          <div className="error" style={{ marginBottom: "15px" }}>
            {error}
          </div>
        )}

        <form onSubmit={handleRename}>
          <div style={{ marginBottom: "15px" }}>
            <label
              style={{
                color: "#f0f0f0",
                display: "block",
                marginBottom: "5px",
              }}
            >
              New Database Name:
            </label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Enter new name"
              style={{
                width: "100%",
                padding: "10px",
                border: "1.5px solid #9370db",
                borderRadius: "5px",
                background: "rgba(147, 112, 219, 0.1)",
                color: "#f0f0f0",
                fontSize: "14px",
              }}
              disabled={loading}
            />
          </div>

          <div style={{ marginBottom: "20px" }}>
            <label
              style={{
                color: "#f0f0f0",
                display: "flex",
                alignItems: "center",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={keepOld}
                onChange={(e) => setKeepOld(e.target.checked)}
                style={{ marginRight: "8px" }}
                disabled={loading}
              />
              Keep old database as backup
            </label>
            <p
              style={{
                color: "#aaa",
                fontSize: "12px",
                marginTop: "5px",
                marginLeft: "24px",
              }}
            >
              If unchecked, the old database will be deleted after successful
              copy
            </p>
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
              onClick={onClose}
              style={{ background: "#6c757d" }}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                background: loading ? "#ccc" : "#9370db",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {loading
                ? keepOld
                  ? "Copying..."
                  : "Renaming..."
                : keepOld
                ? "Copy"
                : "Rename"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default RenameDatabaseModal;
