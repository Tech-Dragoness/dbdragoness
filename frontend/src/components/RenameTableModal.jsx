import React, { useState } from "react";
import axios from "axios";

function RenameTableModal({ dbName, tableName, onClose, onSuccess }) {
  const [newName, setNewName] = useState(tableName + "_copy");
  const [keepOld, setKeepOld] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!newName.match(/^[a-zA-Z][a-zA-Z0-9_]*$/)) {
      setError(
        "Name must start with a letter, contain only letters, numbers, underscores."
      );
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(
        `/api/db/${dbName}/table/${tableName}/rename`,
        {
          new_name: newName,
          keep_old: keepOld,
        }
      );

      if (response.data.success) {
        onSuccess(response.data.new_name);
        onClose();
      } else {
        setError(response.data.error || "Failed to rename table");
      }
    } catch (err) {
      setError(err.response?.data?.error || "Failed to rename table");
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
          width: "90%",
          border: "2px solid #9370db",
          boxShadow: "0 10px 40px rgba(147, 112, 219, 0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ color: "#f0f0f0", marginBottom: "10px" }}>
          Rename/Copy Table
        </h2>
        <p style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "20px" }}>
          Current table: <strong>{tableName}</strong>
        </p>

        {error && (
          <div
            className="error"
            style={{
              marginBottom: "15px",
              padding: "10px",
              background: "rgba(220, 53, 69, 0.2)",
              border: "1px solid #dc3545",
              borderRadius: "5px",
              color: "#ff6b6b",
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "20px" }}>
            <label
              htmlFor="new_name"
              style={{
                color: "#f0f0f0",
                display: "block",
                marginBottom: "5px",
              }}
            >
              New Table Name:
            </label>
            <input
              type="text"
              id="new_name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
              style={{
                width: "100%",
                padding: "10px",
                border: "1.5px solid #9370db",
                borderRadius: "5px",
                background: "rgba(147, 112, 219, 0.1)",
                color: "#f0f0f0",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ marginBottom: "25px" }}>
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
              />
              <span>Keep original table (copy instead of rename)</span>
            </label>
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
              disabled={loading}
              style={{
                padding: "10px 20px",
                background: "#6c757d",
                color: "white",
                border: "none",
                borderRadius: "5px",
                cursor: loading ? "not-allowed" : "pointer",
                fontSize: "14px",
                opacity: loading ? 0.6 : 1,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: "10px 20px",
                background: loading ? "#ccc" : "#9370db",
                color: "white",
                border: "none",
                borderRadius: "5px",
                cursor: loading ? "not-allowed" : "pointer",
                fontSize: "14px",
              }}
            >
              {loading ? "Processing..." : keepOld ? "Copy" : "Rename"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default RenameTableModal;