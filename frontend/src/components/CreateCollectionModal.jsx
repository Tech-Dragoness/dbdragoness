import React, { useState } from "react";
import axios from "axios";

function CreateCollectionModal({ dbName, onClose, onSuccess }) {
  const [collectionName, setCollectionName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!collectionName.match(/^[a-zA-Z][a-zA-Z0-9_]*$/)) {
      setError(
        "Collection name must start with a letter, contain only letters, numbers, underscores."
      );
      return;
    }

    setLoading(true);

    try {
      const response = await axios.post(`/api/db/${dbName}/create_collection`, {
        collection_name: collectionName,
      });

      if (response.data.success) {
        onSuccess(collectionName);
      } else {
        setError(response.data.error || "Failed to create collection");
      }
    } catch (err) {
      setError(
        "Failed to create: " + (err.response?.data?.error || err.message)
      );
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
        backdropFilter: "blur(4px)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1e0033, #3a0066)",
          padding: "40px",
          borderRadius: "15px",
          maxWidth: "600px",
          width: "90%",
          maxHeight: "80vh",
          overflowY: "auto",
          border: "2px solid #9370db",
          boxShadow: "0 10px 40px rgba(147, 112, 219, 0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          style={{
            color: "#f0f0f0",
            margin: "0 0 25px 0",
            textAlign: "center",
          }}
        >
          Create New Collection in {dbName}
        </h2>

        {error && (
          <div
            style={{
              background: "rgba(220, 53, 69, 0.2)",
              color: "#ff8a80",
              padding: "12px",
              borderRadius: "8px",
              borderLeft: "4px solid #dc3545",
              marginBottom: "20px",
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "25px" }}>
            <label
              style={{
                color: "#f0f0f0",
                display: "block",
                marginBottom: "10px",
                fontWeight: "bold",
              }}
            >
              Collection Name:
            </label>
            <input
              type="text"
              value={collectionName}
              onChange={(e) => setCollectionName(e.target.value)}
              placeholder="e.g. users, spells, potions"
              required
              disabled={loading}
              style={{
                width: "100%",
                padding: "14px",
                border: "1.5px solid #9370db",
                borderRadius: "8px",
                background: "rgba(147, 112, 219, 0.15)",
                color: "#f0f0f0",
                fontSize: "16px",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div
            style={{
              background: "rgba(33, 150, 243, 0.15)",
              padding: "16px",
              borderRadius: "10px",
              borderLeft: "4px solid #2196f3",
              color: "#bbdefb",
              marginBottom: "30px",
              fontSize: "0.95em",
            }}
          >
            Collection will be created with no schema. Add documents freely
            after creation.
          </div>

          <div
            style={{ display: "flex", gap: "15px", justifyContent: "flex-end" }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              style={{
                padding: "14px 28px",
                background: "#6c757d",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: "bold",
                opacity: loading ? 0.7 : 1,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: "14px 28px",
                background: loading ? "#7b68b5" : "#9370db",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: "bold",
                boxShadow: loading
                  ? "none"
                  : "0 4px 20px rgba(147, 112, 219, 0.5)",
              }}
            >
              {loading ? "Creating..." : "Create Collection"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateCollectionModal;
